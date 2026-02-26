#!/usr/bin/env python3
"""Search YouTube channels by keyword and filter for active mid-size creators.

Requirements addressed:
- keyword-based search
- channel subscribers between 1k and 20k (configurable)
- consistent uploads (configurable)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode
from urllib.request import urlopen

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass
class ChannelReport:
    channel_id: str
    title: str
    subscribers: int
    total_videos: int
    custom_url: str
    recent_video_count: int
    avg_upload_gap_days: float
    max_upload_gap_days: int
    latest_video_at: Optional[str]


def api_get(path: str, params: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    query = dict(params)
    query["key"] = api_key
    url = f"{YOUTUBE_API_BASE}/{path}?{urlencode(query)}"
    with urlopen(url) as response:  # nosec B310: trusted Google API endpoint
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    if "error" in data:
        message = data["error"].get("message", "unknown error")
        raise RuntimeError(f"YouTube API error: {message}")
    return data


def search_channels(keyword: str, max_results: int, api_key: str) -> List[Dict[str, Any]]:
    data = api_get(
        "search",
        {
            "part": "snippet",
            "type": "channel",
            "q": keyword,
            "maxResults": max_results,
            "order": "relevance",
        },
        api_key,
    )
    return data.get("items", [])


def chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def get_channel_statistics(channel_ids: List[str], api_key: str) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for batch in chunked(channel_ids, 50):
        data = api_get(
            "channels",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "maxResults": 50,
            },
            api_key,
        )
        for item in data.get("items", []):
            result[item["id"]] = item
    return result


def get_recent_upload_dates(playlist_id: str, since: datetime, api_key: str, cap: int = 50) -> List[datetime]:
    dates: List[datetime] = []
    page_token: Optional[str] = None

    while len(dates) < cap:
        params: Dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        data = api_get("playlistItems", params, api_key)
        items = data.get("items", [])
        if not items:
            break

        stop = False
        for item in items:
            published_at = item.get("contentDetails", {}).get("videoPublishedAt")
            if not published_at:
                continue
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if dt < since:
                stop = True
                break
            dates.append(dt)
            if len(dates) >= cap:
                stop = True
                break

        if stop:
            break

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    dates.sort(reverse=True)
    return dates


def analyze_consistency(dates: List[datetime]) -> tuple[int, float, int, Optional[str]]:
    if not dates:
        return 0, float("inf"), 10**9, None
    if len(dates) == 1:
        return 1, float("inf"), 10**9, dates[0].date().isoformat()

    gaps = []
    for earlier, later in zip(dates[:-1], dates[1:]):
        gaps.append((earlier - later).days)
    return (
        len(dates),
        mean(gaps),
        max(gaps),
        dates[0].date().isoformat(),
    )


def build_reports(
    keyword: str,
    api_key: str,
    max_search_results: int,
    min_subs: int,
    max_subs: int,
    lookback_days: int,
    min_recent_videos: int,
    max_gap_days: int,
) -> List[ChannelReport]:
    channels = search_channels(keyword, max_search_results, api_key)
    ids = sorted({item["id"]["channelId"] for item in channels if item.get("id", {}).get("channelId")})

    stats_map = get_channel_statistics(ids, api_key)
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    reports: List[ChannelReport] = []

    for channel_id in ids:
        channel = stats_map.get(channel_id)
        if not channel:
            continue

        statistics = channel.get("statistics", {})
        snippet = channel.get("snippet", {})
        details = channel.get("contentDetails", {})
        uploads_playlist = details.get("relatedPlaylists", {}).get("uploads")
        subscriber_count = int(statistics.get("subscriberCount", 0))

        if subscriber_count < min_subs or subscriber_count > max_subs:
            continue
        if not uploads_playlist:
            continue

        dates = get_recent_upload_dates(uploads_playlist, since, api_key)
        recent_count, avg_gap, max_gap, latest_at = analyze_consistency(dates)

        if recent_count < min_recent_videos:
            continue
        if max_gap > max_gap_days:
            continue

        custom_url = snippet.get("customUrl", "")
        reports.append(
            ChannelReport(
                channel_id=channel_id,
                title=snippet.get("title", ""),
                subscribers=subscriber_count,
                total_videos=int(statistics.get("videoCount", 0)),
                custom_url=f"https://www.youtube.com/{custom_url}" if custom_url else f"https://www.youtube.com/channel/{channel_id}",
                recent_video_count=recent_count,
                avg_upload_gap_days=avg_gap,
                max_upload_gap_days=max_gap,
                latest_video_at=latest_at,
            )
        )

    reports.sort(key=lambda r: (r.subscribers, r.recent_video_count), reverse=True)
    return reports


def print_table(reports: List[ChannelReport]) -> None:
    if not reports:
        print("未找到符合条件的频道。")
        return

    headers = [
        "频道",
        "订阅数",
        "近期待更数",
        "平均间隔(天)",
        "最大间隔(天)",
        "最近更新",
        "链接",
    ]
    print("\t".join(headers))
    for r in reports:
        print(
            "\t".join(
                [
                    r.title,
                    str(r.subscribers),
                    str(r.recent_video_count),
                    f"{r.avg_upload_gap_days:.1f}" if r.avg_upload_gap_days != float("inf") else "-",
                    str(r.max_upload_gap_days if r.max_upload_gap_days < 10**9 else "-"),
                    r.latest_video_at or "-",
                    r.custom_url,
                ]
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按关键词筛选 YouTube 频道（1k-20k 粉丝且持续更新）")
    parser.add_argument("keyword", help="搜索关键词，例如: Christian Creator")
    parser.add_argument("--api-key", default=os.getenv("YOUTUBE_API_KEY"), help="YouTube Data API key（默认读取环境变量 YOUTUBE_API_KEY）")
    parser.add_argument("--max-search-results", type=int, default=50, help="搜索阶段最多拉取多少个频道候选")
    parser.add_argument("--min-subs", type=int, default=1_000, help="最小粉丝数")
    parser.add_argument("--max-subs", type=int, default=20_000, help="最大粉丝数")
    parser.add_argument("--lookback-days", type=int, default=90, help="统计最近多少天的视频发布")
    parser.add_argument("--min-recent-videos", type=int, default=4, help="最近周期内至少发布多少条视频")
    parser.add_argument("--max-gap-days", type=int, default=21, help="视频间最大允许断更天数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_key:
        print("错误：缺少 API key。请通过 --api-key 或环境变量 YOUTUBE_API_KEY 提供。", file=sys.stderr)
        return 2

    reports = build_reports(
        keyword=args.keyword,
        api_key=args.api_key,
        max_search_results=args.max_search_results,
        min_subs=args.min_subs,
        max_subs=args.max_subs,
        lookback_days=args.lookback_days,
        min_recent_videos=args.min_recent_videos,
        max_gap_days=args.max_gap_days,
    )

    if args.json:
        print(json.dumps([r.__dict__ for r in reports], ensure_ascii=False, indent=2))
    else:
        print_table(reports)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
