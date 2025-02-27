from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from mkdocs import utils
from mkdocs.config import base
from mkdocs.config import config_options as c
from .search_index import SearchIndex
from mkdocs.plugins import BasePlugin

log = logging.getLogger(__name__)
base_path = os.path.dirname(os.path.abspath(__file__))


class LangOption(c.OptionallyRequired):
    """Validate Language(s) provided in config are known languages."""

    def get_lunr_supported_lang(self, lang):
        fallback = {'uk': 'ru'}
        for lang_part in lang.split("_"):
            lang_part = lang_part.lower()
            lang_part = fallback.get(lang_part, lang_part)
            if os.path.isfile(os.path.join(base_path, 'lunr-language', f'lunr.{lang_part}.js')):
                return lang_part

    def run_validation(self, value: object):
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise c.ValidationError('Expected a list of language codes.')
        for lang in list(value):
            if lang != 'en':
                lang_detected = self.get_lunr_supported_lang(lang)
                if not lang_detected:
                    log.info(f"Option search.lang '{lang}' is not supported, falling back to 'en'")
                    value.remove(lang)
                    if 'en' not in value:
                        value.append('en')
                elif lang_detected != lang:
                    value.remove(lang)
                    value.append(lang_detected)
                    log.info(f"Option search.lang '{lang}' switched to '{lang_detected}'")
        return value


class _PluginConfig(base.Config):
    lang = c.OptionallyRequired(LangOption())
    separator = c.Type(str, default=r'[\s\-]+')
    min_search_length = c.Type(int, default=3)
    prebuild_index = c.Choice((False, True, 'node', 'python'), default=False)
    indexing = c.Choice(('full', 'sections', 'titles'), default='full')


class SearchPlugin(BasePlugin):
    """Add a search feature to MkDocs."""

    def on_config(self, config, **kwargs) -> Any:
        "Add plugin templates and scripts to config."
        if 'include_search_page' in config['theme'] and config['theme']['include_search_page']:
            config['theme'].static_templates.add('search.html')
        if not ('search_index_only' in config['theme'] and config['theme']['include_search_page']):
            path = os.path.join(base_path, 'templates')
            config['theme'].dirs.append(path)
            if 'search/main.js' not in config['extra_javascript']:
                 config['extra_javascript'].append('search/main.js')
        
        return config

    def on_pre_build(self, config, **kwargs):
        "Create search index instance for later use."
        self.search_index = SearchIndex(**self.config)

    def on_page_context(self, context, **kwargs):
        "Add page to search index."
        self.search_index.add_entry_from_context(context['page'])

    def on_post_build(self, config, **kwargs) -> None:
        "Build search index."
        output_base_path = os.path.join(config['site_dir'], 'search')
        search_index = self.search_index.generate_search_index()
        json_output_path = os.path.join(output_base_path, 'search_index.json')
        utils.write_file(search_index.encode('utf-8'), json_output_path)

        assert self.config['lang'] is not None
        if not ('search_index_only' in config['theme'] and config['theme']['search_index_only']):
            # Include language support files in output. Copy them directly
            # so that only the needed files are included.
            files = []
            if len(self.config['lang']) > 1 or 'en' not in self.config['lang']:
                files.append('lunr.stemmer.support.js')
            if len(self.config['lang']) > 1:
                files.append('lunr.multi.js')
            if 'ja' in self.config['lang'] or 'jp' in self.config['lang']:
                files.append('tinyseg.js')
            for lang in self.config['lang']:
                if lang != 'en':
                    files.append(f'lunr.{lang}.js')

            for filename in files:
                from_path = os.path.join(base_path, 'lunr-language', filename)
                to_path = os.path.join(output_base_path, filename)
                utils.copy_file(from_path, to_path)
