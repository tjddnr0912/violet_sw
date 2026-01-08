"""
News Bot Module
---------------
News aggregation, AI summarization, and blog posting
"""

from .config import config
from .aggregator import NewsAggregator
from .summarizer import AISummarizer
from .writer import MarkdownWriter

__all__ = ['config', 'NewsAggregator', 'AISummarizer', 'MarkdownWriter']
