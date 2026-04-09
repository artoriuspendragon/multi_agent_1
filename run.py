#!/usr/bin/env python3
"""
项目启动脚本：一键执行完整 pipeline。

用法：
  python3 run.py
  python3 run.py --config config.yaml
  python3 run.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="私人消息流推送助手 - 运行一次 pipeline")
    p.add_argument(
        "--config",
        default=None,
        help="配置文件路径。默认读取 CONFIG_PATH 环境变量，再默认 ./config.yaml",
    )
    p.add_argument(
        "--timeout-per-source",
        type=int,
        default=30,
        help="单个 source 拉取超时（秒），默认 30",
    )
    p.add_argument(
        "--dedup-key",
        choices=["link", "raw_id"],
        default="link",
        help="去重键，默认 link",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="打印更详细日志",
    )
    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    # 让 `python3 run.py` 可直接 import src/app
    root = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(root, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    try:
        from app import load_config, run
        from app.config import ConfigLoadError
    except Exception as e:
        print(f"[FATAL] import failed: {e}")
        return 2

    try:
        cfg = load_config(args.config)
    except Exception as e:
        print(f"[FATAL] config load failed: {e}")
        return 2

    result = run(
        cfg,
        timeout_per_source=args.timeout_per_source,
        dedup_key=args.dedup_key,
    )

    print("=" * 60)
    print("Pipeline Result")
    print("=" * 60)
    print(f"ok: {result.ok}")
    print(f"steps_completed: {result.steps_completed}")
    print(f"raw_count: {result.raw_count}")
    print(f"dedup_count: {result.dedup_count}")
    print(f"filtered_count: {result.filtered_count}")
    print(f"push_success_count: {result.push_success_count}")
    if result.digest:
        print(f"digest_title: {result.digest.title}")
    if result.channel_results:
        print("channel_results:")
        for r in result.channel_results:
            print(f"  - {r.channel_type}: success={r.success}, error={r.error}")
    if result.errors:
        print("errors:")
        for e in result.errors:
            print(f"  - {e}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

