# -*- coding: utf-8 -*-
#
# Copyright © 2016 Mathieu Duponchelle <mathieu.duponchelle@opencreed.com>
# Copyright © 2016 Collabora Ltd
#
# This library is free software; you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; either version 2.1 of the License, or (at your option)
# any later version.
#
# This library is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library.  If not, see <http://www.gnu.org/licenses/>.

import os
import shutil

from collections import defaultdict
from collections import OrderedDict
from lxml import etree

from hotdoc.core.base_extension import BaseExtension
from hotdoc.core.base_formatter import Formatter
from hotdoc.core.symbols import *
from hotdoc.utils.loggable import error
from hotdoc.utils.utils import recursive_overwrite

DESCRIPTION =\
"""
An extension to generate devhelp indexes.
"""

BOILERPLATE=\
u"""<?xml version="1.0"?>
<!DOCTYPE book PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "">
<book xmlns="http://www.devhelp.net/book" title="%s" link="%s" \
author="hotdoc" name="%s" version="2" language="%s"/>
"""

HERE = os.path.dirname(__file__)

class FormattedSymbol(object):
    def __init__(self, sym, subfolder):
        self.type_ = TYPE_MAP.get(type(sym))
        self.ref = os.path.join(subfolder, sym.link.ref)
        self.display_name = sym.link.title


class FormattedPage(object):
    def __init__(self, page, subfolder):
        self.source_file = page.source_file
        self.formatted_symbols = []
        self.full_ref = os.path.join(subfolder, page.link.ref)
        self.title = page.get_title() or 'missing-title'
        for symbol in page.symbols:
            if not symbol.skip:
                self.formatted_symbols.append(
                    FormattedSymbol(symbol, subfolder))


TYPE_MAP = {
    FunctionSymbol: 'function',
    StructSymbol: 'struct',
    EnumSymbol: 'enum',
    PropertySymbol: 'property',
    SignalSymbol: 'signal',
    ConstantSymbol: 'macro',
    FunctionMacroSymbol: 'macro',
    CallbackSymbol: 'function'
}


class DevhelpExtension(BaseExtension):
    EXTENSION_NAME='devhelp-extension'
    argument_prefix='devhelp'
    activated = False

    def __init__(self, doc_repo):
        BaseExtension.__init__(self, doc_repo)
        self.__formatted_pages = defaultdict(list)
        self.__ext_languages = defaultdict(set)

    def __writing_page_cb(self, formatter, page, path):
        relpath = os.path.relpath(path, self.doc_repo.output)
        language = ''
        if page.languages:
            language = page.languages[0]
        key = page.extension_name + '-' + (language or '')

        self.__ext_languages[page.extension_name].add(language)

        self.__formatted_pages[key].append(FormattedPage(page,
            os.path.dirname(relpath)))

    def __format_chapters(self, doc_tree, pnode, page, html_path, fpages):
        for name in page.subpages:
            cpage = doc_tree.pages[name]
            if cpage.extension_name != page.extension_name:
                continue
            fpage = fpages[cpage.source_file]
            ref = os.path.join(html_path, fpage.full_ref)
            node = etree.Element('sub',
                attrib = {'name': fpage.title,
                          'link': ref})
            pnode.append(node)
            self.__format_chapters(doc_tree, node, cpage, html_path, fpages)

    def __format_index(self, doc_tree, page, language):
        key = page.extension_name + '-' + (language or '')
        fpages = self.__formatted_pages[key]

        oname = self.doc_repo.project_name
        if self.doc_repo.project_version:
            oname += '-%s' % self.doc_repo.project_version

        if page.extension_name != 'core':
            oname += '-%s' % page.extension_name

        if language:
            oname += '-%s' % language

        opath = os.path.join(self.doc_repo.output, 'devhelp', oname)

        if not os.path.exists(opath):
            os.makedirs(opath)

        opath = os.path.join(opath, oname + '.devhelp2')

        html_path = os.path.join('..', self.doc_repo.project_name + '-html')

        findex = None
        funcs_node = etree.Element('functions')
        fpage_map = {}
        for fpage in fpages:
            fpage_map[fpage.source_file] = fpage
            if fpage.source_file == page.source_file:
                findex = fpage
            for sym in fpage.formatted_symbols:
                if sym.type_ is None:
                    continue
                node = etree.Element('keyword',
                    attrib={'type': sym.type_,
                            'name': sym.display_name,
                            'link': os.path.join(html_path, sym.ref)})
                funcs_node.append(node)

        chapter_node = etree.Element('chapters')
        self.__format_chapters(doc_tree, chapter_node, page, html_path,
            fpage_map)

        full_ref = os.path.join(html_path, findex.full_ref)

        title = '%s %s' % (self.doc_repo.project_name, page.get_title())
        if language:
            title += ' (%s)' % language

        boilerplate = BOILERPLATE % (
            title,
            full_ref,
            oname,
            language)

        root = etree.fromstring(boilerplate)
        root.append(chapter_node)
        root.append(funcs_node)
        tree = etree.ElementTree(root)

        tree.write(opath, pretty_print=True,
            encoding='utf-8', xml_declaration=True)

    def __format_subtree(self, doc_tree, page):
        for l in self.__ext_languages[page.extension_name]:
            self.__format_index(doc_tree, page, l)

    def __formatted_cb(self, doc_repo):
        formatter = self.doc_repo.extensions['core'].get_formatter('html')
        html_path = os.path.join(self.doc_repo.output,
                formatter.get_output_folder())

        oname = doc_repo.project_name + '-html'

        dh_html_path = os.path.join(self.doc_repo.output, 'devhelp',
            oname, formatter.get_output_folder())

        recursive_overwrite(html_path, dh_html_path)

        # Remove some stuff not relevant in devhelp
        with open(os.path.join(dh_html_path, 'assets', 'css',
            'devhelp.css'), 'w') as _:
            _.write('[data-hotdoc-role="navigation"] {display: none;}\n')
        shutil.rmtree(os.path.join(dh_html_path, 'assets', 'js'))

        for page in doc_repo.doc_tree.walk():
            if page.is_root:
                self.__format_subtree(doc_repo.doc_tree, page)

    def __formatting_page_cb(self, formatter, page):
        page.output_attrs['html']['stylesheets'].add(
            os.path.join(HERE, 'devhelp.css'))

    def setup(self):
        if not DevhelpExtension.activated:
            return

        # FIXME update the index someday.
        if self.doc_repo.incremental:
            return

        Formatter.writing_page_signal.connect(self.__writing_page_cb)
        Formatter.formatting_page_signal.connect(self.__formatting_page_cb)
        self.doc_repo.formatted_signal.connect_after(self.__formatted_cb)

    @staticmethod
    def add_arguments(parser):
        group = parser.add_argument_group('Devhelp extension',
                DESCRIPTION)
        group.add_argument('--devhelp-activate', action="store_true",
                help="Activate the devhelp extension", dest='devhelp_activate')

    @staticmethod
    def parse_config(doc_repo, config):
        DevhelpExtension.activated = bool(config.get('devhelp_activate', False))
        if DevhelpExtension.activated and config.get('project_name', None) is None:
            error('invalid-config',
                'To activate the devhelp extension, --project-name has to be '
                'specified.')


def get_extension_classes():
    return [DevhelpExtension]
