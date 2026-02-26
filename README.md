# ChristianCreator YouTube 筛选工具

根据关键词搜索 YouTube 频道，并筛选出：
- 粉丝量在 **1k ~ 20k** 区间
- 最近一段时间有稳定更新（默认 90 天内至少 4 条，且最大断更不超过 21 天）

## 使用前准备

1. 创建 YouTube Data API v3 Key。
2. 设置环境变量：

```bash
export YOUTUBE_API_KEY="你的key"
```

## 使用示例

```bash
python3 youtube_christian_creator_finder.py "Christian Creator"
```

输出列包括频道名、订阅数、最近更新数量、更新间隔、最近更新时间和频道链接。

## 常用参数

- `--min-subs` / `--max-subs`：粉丝区间（默认 1000 / 20000）
- `--lookback-days`：统计窗口天数（默认 90）
- `--min-recent-videos`：最近窗口最少发布数（默认 4）
- `--max-gap-days`：最大断更天数（默认 21）
- `--json`：以 JSON 输出

示例：

```bash
python3 youtube_christian_creator_finder.py "Christian Creator" \
  --min-subs 1000 --max-subs 20000 \
  --lookback-days 120 --min-recent-videos 5 --max-gap-days 21 --json
```
