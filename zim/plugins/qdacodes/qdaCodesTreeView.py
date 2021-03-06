# -*- coding: utf-8 -*-

# Copyright 2014 Dario Gomez  <dariogomezt at gmail dot com>
# Licence : GPL or same as Zim

from __future__ import with_statement

import gtk
import pango
import re


from zim.notebook import Path
from zim.gui.widgets import ui_environment, BrowserTreeView, encode_markup_text, decode_markup_text
from zim.gui.clipboard import Clipboard

from qdaSettings import logger, _tag_re, _NO_TAGS, NOTE_MARK, NOTE_AUTOTITLE, sluglify

import zim.datetimetz as datetime

# Borrar
_date_re = re.compile(r'\s*\[d:(.+)\]')
_NO_DATE = '9999'  # Constant for empty due date - value chosen for sorting properties


HIGH_COLOR = '#EF5151'  # red (derived from Tango style guide - #EF2929)
MEDIUM_COLOR = '#FCB956'  # orange ("idem" - #FCAF3E)
ALERT_COLOR = '#FCEB65'  # yellow ("idem" - #FCE94F)
# FIXME: should these be configurable ?


class QdaCodesTreeView(BrowserTreeView):

    MCOL_VISI = 0
    MCOL_CODE = 1
    MCOL_CITA = 2
    MCOL_PAGE = 3
    MCOL_NCIT = 4
    MCOL_RGID = 5
    MCOL_TAGS = 6

    def getColIx(self):
        self.colIx += 1
        return self.colIx - 1

    def __init__(self, ui, plugin):

        # Visible, MCOL_CODE, MCOL_CITA, MCOL_PAGE, MCOL_NCIT, MCOL_RGID, MCOL_TAGS
        self.real_model = gtk.TreeStore(bool, str, str, str, str, int, object)
        model = self.real_model.filter_new()
        model.set_visible_column(self.MCOL_VISI)
        model = gtk.TreeModelSort(model)

        BrowserTreeView.__init__(self, model)
        self.ui = ui
        self.plugin = plugin
        self.filter = None
        self.tag_filter = None
        self.label_filter = None
        self._tags = {}
        self._labels = {}


# Description column
        cell_renderer = gtk.CellRendererText()
        cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)

        column = gtk.TreeViewColumn(_('QdaCode'), cell_renderer, markup=self.MCOL_CODE)
        column.set_resizable(True)
        column.set_sort_column_id(self.MCOL_CODE)
        column.set_expand(True)
        column.set_min_width(200)
        self.append_column(column)
        self.set_expander_column(column)

# Citation  column
        cell_renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_('Text'), cell_renderer, text=self.MCOL_CITA)

        column.set_resizable(True)
        column.set_sort_column_id(self.MCOL_CITA)
        column.set_min_width(200)
        column.set_max_width(300)

        self.append_column(column)

# Rendering for page name column
        cell_renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_('Page'), cell_renderer, text=self.MCOL_PAGE)
        column.set_sort_column_id(self.MCOL_PAGE)
        self.append_column(column)


# Nro Citation in the page
        cell_renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_(' # '), cell_renderer, text=self.MCOL_NCIT)
        column.set_sort_column_id(self.MCOL_NCIT)
        self.append_column(column)


# Finalize
        self.refresh()

        # HACK because we can not register ourselves :S
        self.connect('row_activated', self.__class__.do_row_activated)


    def refresh(self):
        '''Refresh the model based on index data'''
        # Update data
        self._clear()
        self._append_codes(None, None, {})

        # Make tags case insensitive
        tags = sorted((t.lower(), t) for t in self._tags)
        prev = ('', '')
        for tag in tags:
            if tag[0] == prev[0]:
                self._tags[prev[1]] += self._tags[tag[1]]
                self._tags.pop(tag[1])
            prev = tag

        # Set view
        self._eval_filter()  # keep current selection
        self.expand_all()

    def _clear(self):
        self.real_model.clear()  # flush
        self._tags = {}
        self._labels = {}

    def _append_codes(self, code, iter, path_cache):
        """ Agrega los codigos en la ventana 
        """

        sWhere = self._getWStmt(self.plugin.preferences['qda_labels'])
        sOrder = 'source, citnumber'

        for row in self.plugin.list_codes(parent=code, orderBy=sOrder, whereStmt=sWhere):

            if row['source'] not in path_cache:
                path = self.plugin.get_path(row)
                if path is None:
                    continue
                else:
                    path_cache[row['source']] = path

            path = path_cache[row['source']]

            # Update labels
            label = row['tag']
            self._labels[label] = self._labels.get(label, 0) + 1

            # Update tag count
            tags = path.parts
            for tag in tags:
                self._tags[tag] = self._tags.get(tag, 0) + 1

            #  Code ( description )
            nroCita = "{0:03d}".format(row['citnumber'])
            description = self.get_code_description(row)

            # Insert all columns
            # Visible, MCOL_CODE, MCOL_CITA, MCOL_PAGE, MCOL_NCIT, MCOL_RGID, MCOL_TAGS
            modelrow = [ True, description , row['citation'].replace('\n', ';')  , path.name, nroCita, row['id'], tags ]

            modelrow[0] = self._filter_item(modelrow)
            myiter = self.real_model.append(iter, modelrow)

    def get_code_description(self, row):
        """ Linea de descripcion de codigo
        """
        # return '{0}{1} {2}'.format(NOTE_MARK, row['tag'], row['description'])
        return '{0}{1} {2}'.format('', row['tag'], row['description'])

    def set_filter(self, string):
        # FIXME FILTER allow more complex queries here - same parse as for search
        if string:
            inverse = False
            # if string.lower().startswith('not '):
            #     # Quick HACK to support e.g. "not @waiting"
            #     inverse = True
            #     string = string[4:]

            self.filter = (inverse, string.strip().lower())
        else:
            self.filter = None
        self._eval_filter()

    def get_labels(self):
        '''Get all labels that are in use
        @returns: a dict with labels as keys and the number of codes
        per label as value
        '''
        return self._labels

    def get_tags(self):
        '''Get all tags that are in use
        @returns: a dict with filenames as keys and the number of codes
        per tag as value
        '''
# 		return self._tags
        return {}

    def get_n_codes(self):
        '''Get the number of codes in the list
        @returns: total number
        '''
        counter = [0]
        def count(model, path, iter):
            counter[0] += 1
        self.real_model.foreach(count)
        return counter[0]


    def set_tag_filter(self, tags=None, labels=None):
        if tags:
            self.tag_filter = [tag.lower() for tag in tags]
        else:
            self.tag_filter = None

        if labels:
            self.label_filter = [label.lower() for label in labels]
        else:
            self.label_filter = None

        self._eval_filter()

    def _eval_filter(self):
        logger.debug('Filtering with labels: %s tags: %s, filter: %s', self.label_filter, self.tag_filter, self.filter)

        def filter(model, path, iter):
            visible = self._filter_item(model[iter])
            model[iter][self.MCOL_VISI] = visible
            if visible:
                parent = model.iter_parent(iter)
                while parent:
                    model[parent][self.MCOL_VISI] = visible
                    parent = model.iter_parent(parent)

        self.real_model.foreach(filter)
        self.expand_all()

    def _filter_item(self, modelrow):
        # This method filters case insensitive because both filters and
        # text are first converted to lower case text.


        description = modelrow[self.MCOL_CODE].decode('utf-8').lower()
        pagename = modelrow[self.MCOL_PAGE].decode('utf-8').lower()
        tags = [t.lower() for t in modelrow[self.MCOL_TAGS]]

        visible = True
        if self.label_filter:
            # Any labels need to be present
            for label in self.label_filter:
                if label in description:
                    break
            else:
                visible = False  # no label found

        if visible and self.tag_filter:
            # Any tag should match
            if (_NO_TAGS in self.tag_filter and not tags) \
            or any(tag in tags for tag in self.tag_filter):
                visible = True
            else:
                visible = False

        if visible and self.filter:
            # And finally the filter string should match
            # FIXME: FILTER: manejo de filtro a dif nivlkes
            inverse, filterStmt = self.filter
            lStmt = filterStmt.split() 
            for stmt in lStmt: 
                inverse = False 
                if stmt.lower()[0] in ('!', '-')  :
                    inverse = True
                    stmt = stmt[1:]
            
                match = stmt in description or stmt in pagename 
                if (not inverse and not match) or (inverse and match):
                    visible = False
                    break 

        return visible

    def do_row_activated(self, path, column):
        model = self.get_model()
        page = Path(model[path][self.MCOL_PAGE])
        text = self._get_raw_text(model[path])
        self.ui.open_page(page)
        self.ui.mainwindow.pageview.find(text)

    def _get_raw_text(self, code):
        id = code[self.MCOL_RGID]
        row = self.plugin.get_code(id)
        return self.get_code_description(row)

    def do_initialize_popup(self, menu):
        item = gtk.ImageMenuItem('gtk-copy')
        item.connect('activate', self.copy_to_clipboard)
        menu.append(item)
        self.populate_popup_expand_collapse(menu)

    def copy_to_clipboard(self, *a):
        '''Exports currently visible elements from the codes list'''
        logger.debug('Exporting to clipboard current view of qda codes.')
        text = self.get_visible_data_as_csv()
        Clipboard.set_text(text)
            # TODO set as object that knows how to format as text / html / ..
            # unify with export hooks

    def get_visible_data_as_csv(self):
        text = ""
#         for indent, prio, desc, date, page in self.get_visible_data():
        for indent, desc, date, page in self.get_visible_data():
            desc = decode_markup_text(desc)
            desc = '"' + desc.replace('"', '""') + '"'
#             text += ",".join((prio, desc, date, page)) + "\n"
            text += ",".join((desc, date, page)) + "\n"
        return text


    def get_visible_data(self):
        rows = []

        def collect(model, path, iter):
            indent = len(path) - 1  # path is tuple with indexes

            row = model[iter]
#             prio = row[self.MCOL_NCIT]
            code = row[self.MCOL_CODE].decode('utf-8')
            cita = row[self.MCOL_CITA].decode('utf-8').replace('\n', ';')
            page = row[self.MCOL_PAGE].decode('utf-8')

            rows.append((indent, code, cita, page))

        model = self.get_model()
        model.foreach(collect)

        return rows

    def _getWStmt(self, baseWhere):
        """ Toma los codigos definidos en la conf y los coviernte en un where, 
            en caso de q todos las marcas se tomen como codigos,  solo elimina los titulos (schema)
        """

        sWhere = 'tag != \'{}\''.format( NOTE_AUTOTITLE )
        if len( baseWhere ) > 0: 
            sWhere = ''
            for s in baseWhere.split(','):
                sWhere += '\'{}\','.format(s.strip().upper())
    
            sWhere = 'tag in ({})'.format(sWhere[:-1])

        return sWhere



    def get_data_as_page(self, me):
        """ Opcion de exportacion  llamada desde el boton de la ventana 
        """
        
        from qdaExport import doQdaExport  
        qdaExp =  doQdaExport( self   )
        qdaExp.do_exportQdaCodes()
        
