"""
web 包：将 Digest 渲染为可发布的网页。

- paper.render_paper：拟物（skeuomorphism）报纸风格、可交互的早报网页
"""

from __future__ import annotations

from .paper import render_paper

__all__ = ["render_paper"]
