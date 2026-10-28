# This file is part of dcVector.
#
# Copyright (c) 2025-2026 Sébastien Chognard
# Copyright (c) 2025-2026 University of Geneva
# SPDX-License-Identifier: Apache-2.0
"""
Interactive visualisation tools for vector data loaded from the datacube.

This module provides:

- ``Legend``: reads the legends stored in the metadata of a vector product and
  converts them into colour schemes usable by matplotlib, holoviews or ipyleaflet.
- ``TemporalMapViewer``: an ipyleaflet map with a time slider to browse a time
  series of vector data.
"""
from ipyleaflet import Map, GeoData, basemaps, LayersControl, Choropleth, GeoJSON, LegendControl, CircleMarker
import leafmap
import geopandas as gpd
import pandas as pd
from datetime import datetime
import json
import re
import numpy as np
from branca.colormap import linear
import ipywidgets as widgets
import math
CSS_COLORS = {
    'aliceblue': '#f0f8ff',
    'antiquewhite': '#faebd7',
    'aqua': '#00ffff',
    'aquamarine': '#7fffd4',
    'azure': '#f0ffff',
    'beige': '#f5f5dc',
    'bisque': '#ffe4c4',
    'black': '#000000',
    'blanchedalmond': '#ffebcd',
    'blue': '#0000ff',
    'blueviolet': '#8a2be2',
    'brown': '#a52a2a',
    'burlywood': '#deb887',
    'cadetblue': '#5f9ea0',
    'chartreuse': '#7fff00',
    'chocolate': '#d2691e',
    'coral': '#ff7f50',
    'cornflowerblue': '#6495ed',
    'cornsilk': '#fff8dc',
    'crimson': '#dc143c',
    'cyan': '#00ffff',
    'darkblue': '#00008b',
    'darkcyan': '#008b8b',
    'darkgoldenrod': '#b8860b',
    'darkgray': '#a9a9a9',
    'darkgreen': '#006400',
    'darkkhaki': '#bdb76b',
    'darkmagenta': '#8b008b',
    'darkolivegreen': '#556b2f',
    'darkorange': '#ff8c00',
    'darkorchid': '#9932cc',
    'darkred': '#8b0000',
    'darksalmon': '#e9967a',
    'darkseagreen': '#8fbc8f',
    'darkslateblue': '#483d8b',
    'darkslategray': '#2f4f4f',
    'darkturquoise': '#00ced1',
    'darkviolet': '#9400d3',
    'deeppink': '#ff1493',
    'deepskyblue': '#00bfff',
    'dimgray': '#696969',
    'dodgerblue': '#1e90ff',
    'firebrick': '#b22222',
    'floralwhite': '#fffaf0',
    'forestgreen': '#228b22',
    'fuchsia': '#ff00ff',
    'gainsboro': '#dcdcdc',
    'ghostwhite': '#f8f8ff',
    'gold': '#ffd700',
    'goldenrod': '#daa520',
    'gray': '#808080',
    'green': '#008000',
    'greenyellow': '#adff2f',
    'honeydew': '#f0fff0',
    'hotpink': '#ff69b4',
    'indianred': '#cd5c5c',
    'indigo': '#4b0082',
    'ivory': '#fffff0',
    'khaki': '#f0e68c',
    'lavender': '#e6e6fa',
    'lavenderblush': '#fff0f5',
    'lawngreen': '#7cfc00',
    'lemonchiffon': '#fffacd',
    'lightblue': '#add8e6',
    'lightcoral': '#f08080',
    'lightcyan': '#e0ffff',
    'lightgoldenrodyellow': '#fafad2',
    'lightgray': '#d3d3d3',
    'lightgreen': '#90ee90',
    'lightpink': '#ffb6c1',
    'lightsalmon': '#ffa07a',
    'lightseagreen': '#20b2aa',
    'lightskyblue': '#87cefa',
    'lightslategray': '#778899',
    'lightsteelblue': '#b0c4de',
    'lightyellow': '#ffffe0',
    'lime': '#00ff00',
    'limegreen': '#32cd32',
    'linen': '#faf0e6',
    'magenta': '#ff00ff',
    'maroon': '#800000',
    'mediumaquamarine': '#66cdaa',
    'mediumblue': '#0000cd',
    'mediumorchid': '#ba55d3',
    'mediumpurple': '#9370db',
    'mediumseagreen': '#3cb371',
    'mediumslateblue': '#7b68ee',
    'mediumspringgreen': '#00fa9a',
    'mediumturquoise': '#48d1cc',
    'mediumvioletred': '#c71585',
    'midnightblue': '#191970',
    'mintcream': '#f5fffa',
    'mistyrose': '#ffe4e1',
    'moccasin': '#ffe4b5',
    'navajowhite': '#ffdead',
    'navy': '#000080',
    'oldlace': '#fdf5e6',
    'olive': '#808000',
    'olivedrab': '#6b8e23',
    'orange': '#ffa500',
    'orangered': '#ff4500',
    'orchid': '#da70d6',
    'palegoldenrod': '#eee8aa',
    'palegreen': '#98fb98',
    'paleturquoise': '#afeeee',
    'palevioletred': '#db7093',
    'papayawhip': '#ffefd5',
    'peachpuff': '#ffdab9',
    'peru': '#cd853f',
    'pink': '#ffc0cb',
    'plum': '#dda0dd',
    'powderblue': '#b0e0e6',
    'purple': '#800080',
    'red': '#ff0000',
    'rosybrown': '#bc8f8f',
    'royalblue': '#4169e1',
    'saddlebrown': '#8b4513',
    'salmon': '#fa8072',
    'sandybrown': '#f4a460',
    'seagreen': '#2e8b57',
    'seashell': '#fff5ee',
    'sienna': '#a0522d',
    'silver': '#c0c0c0',
    'skyblue': '#87ceeb',
    'slateblue': '#6a5acd',
    'slategray': '#708090',
    'snow': '#fffafa',
    'springgreen': '#00ff7f',
    'steelblue': '#4682b4',
    'tan': '#d2b48c',
    'teal': '#008080',
    'thistle': '#d8bfd8',
    'tomato': '#ff6347',
    'turquoise': '#40e0d0',
    'violet': '#ee82ee',
    'wheat': '#f5deb3',
    'white': '#ffffff',
    'whitesmoke': '#f5f5f5',
    'yellow': '#ffff00',
    'yellowgreen': '#9acd32'}

from jsonschema import validate, ValidationError

# =========================
# JSON SCHEMAS
# =========================

UNIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "color": {
            "type": "string",
            "pattern": "^#(?:[0-9a-fA-F]{3}){1,2}$"
        }
    },
    "required": ["color"],
    "additionalProperties": False
}

CONTINUOUS_SCHEMA = {
    "type": "object",
    "properties": {
        "codeName": {
            "type": "string"
        }
    },
    "required": ["codeName"],
    "additionalProperties": False
}

CLASS_SCHEMA = {
    "type": "object",
    "properties": {
        "value": {
            "anyOf": [
                {"type": "number"},
                {"type": "string"}
            ]
        },
        "name": {
            "type": "string"
        },
        "color": {
            "type": "string",
            "pattern": "^#(?:[0-9a-fA-F]{3}){1,2}$"
        }
    },
    "required": ["value", "name", "color"],
    "additionalProperties": False
}

RANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "valueMin": {
            "type": "number"
        },
        "valueMax": {
            "type": "number"
        },
        "name": {
            "type": "string"
        },
        "color": {
            "type": "string",
            "pattern": "^#(?:[0-9a-fA-F]{3}){1,2}$"
        }
    },
    "required": ["valueMin", "valueMax", "name", "color"],
    "additionalProperties": False
}



class Legend:
    
    """
    Legends of a vector product.

    A ``Legend`` is built from the ``legend`` list stored in the product metadata,
    which is available in the ``attrs['legend']`` attribute of the GeoDataFrame
    returned by ``Datacube.load_vect``. Each legend is a dict with the keys:

    - ``name``: name of the legend (e.g. ``"niveau 1"``);
    - ``legendType``: ``"class"``, ``"range"``, ``"unique"`` or ``"continuous"``;
    - ``fieldToApply``: list of the attribute fields the legend applies to;
    - ``legendItem``: list of legend items (value or value range, name and colour).

    Colours can be given as hexadecimal codes (``"#ff0000"``), RGB triplets
    (``[255, 0, 0]``) or CSS colour names (``"red"``).
    """
    def __init__(self,metadataLegend):
        #metadataLegendDict = {k: v for d in metadataLegend for k, v in d.items()}
        #self.legendType=metadataLegendDict['legendType'] if 'legendType' in metadataLegendDict.keys() else None
        #self.fieldToApply=metadataLegendDict['fieldToApply'] if 'fieldToApply' in metadataLegendDict.keys() else None
        #self.legendItem=metadataLegendDict['legendItem'] if 'legendItem' in metadataLegendDict.keys() else None
        """
        Args:
            metadataLegend (list of dict): legends as stored in the product metadata.
        """
        self.legendList=metadataLegend
        self.defaultColor='#fff'
        self.list_legend={element['name']:{'type':element['legendType'],'field':element['fieldToApply'],'items':element['legendItem']} for element in metadataLegend}
    def _createRangeColorscheme(self,legendDict) -> dict :
        """
        Build the conditions and colours of a ``range`` legend.

        Args:
            legendDict (list of dict): legend items with ``valueMin`` and/or
                ``valueMax`` and ``color``.

        Returns:
            dict: ``{'conditions': [...], 'choices': [...]}``, where each condition is
            a function ``(gdf, column) -> boolean Series`` and each choice is the
            corresponding hexadecimal colour.
        """
        conditions=[]
        choices=[]
        for element in legendDict:
            if 'valueMin' in element.keys() and 'valueMax' in element.keys():
                conditions.append(lambda gdf, col, min_val=element['valueMin'], max_val=element['valueMax']: (gdf[col] >= min_val) & (gdf[col] <= max_val))
                choices.append(self._translateToHex(element['color']))
            elif 'valueMin' in element.keys() and 'valueMax' not in element.keys():
                conditions.append(lambda gdf, col, min_val=element['valueMin']: (gdf[col] >= min_val))
                choices.append(self._translateToHex(element['color']))
            elif 'valueMin' not in element.keys() and 'valueMax' in element.keys():
                conditions.append(lambda gdf, col,  max_val=element['valueMax']: (gdf[col] <= max_val))
                choices.append(self._translateToHex(element['color']))
        return {'conditions':conditions,'choices':choices}

    @staticmethod
    def detect_colorscheme_type(colorscheme):

        # Case 1: unique
        """
        Detect the type of a colour scheme from its structure.

        Args:
            colorscheme (dict or list): colour scheme to test.

        Returns:
            str: ``"unique"`` (``{'color': ...}``), ``"continuous"``
            (``{'codeName': ...}``), ``"class"`` (list of ``{'value', 'name', 'color'}``)
            or ``"range"`` (list of ``{'valueMin', 'valueMax', 'name', 'color'}``).

        Raises:
            ValueError: if the colour scheme matches none of these formats.
        """
        try:
            validate(instance=colorscheme, schema=UNIQUE_SCHEMA)
            return "unique"
        except ValidationError:
            pass

        # Case 2: continuous
        try:
            validate(instance=colorscheme, schema=CONTINUOUS_SCHEMA)
            return "continuous"
        except ValidationError:
            pass

        # Case 3: class
        if isinstance(colorscheme, list):
            try:
                for item in colorscheme:
                    validate(instance=item, schema=CLASS_SCHEMA)
                return "class"
            except ValidationError:
                pass

        # Case 4: range
        if isinstance(colorscheme, list):
            try:
                for item in colorscheme:
                    validate(instance=item, schema=RANGE_SCHEMA)
                return "range"
            except ValidationError:
                pass

        raise ValueError("Invalid colorscheme format")

    def _createClassColorscheme(self,legendDict) ->dict:
        """
        Build the conditions and colours of a ``class`` legend.

        Args:
            legendDict (list of dict): legend items with ``value`` and ``color``.

        Returns:
            dict: ``{'conditions': [...], 'choices': [...]}``, where each condition is
            a function ``(gdf, column) -> boolean Series`` testing equality with the
            class value and each choice is the corresponding hexadecimal colour.
        """
        conditions=[]
        choices=[]
        for element in legendDict:
            conditions.append(lambda gdf,col,val=element['value']:(gdf[col]==val))
            choices.append(self._translateToHex(element['color']))
        return {'conditions':conditions,'choices':choices}
    def set_defaultColor(self,color):
        """
        Set the colour used for features that match no legend item.

        Args:
            color (str, list or tuple): hexadecimal code, RGB triplet or CSS colour name.
        """
        self.defaultColor=self._translateToHex(color)
    @property
    def get_defaultColor(self):
        """
        str: Hexadecimal colour used for features that match no legend item.
        """
        return self.defaultColor
    @property
    def get_list_name(self) -> list:
        """
        list of str: Names of the available legends.
        """
        return list(self.list_legend.keys())
        #return [element['name'] for element in self.legendList]
    @property
    def get_list_colors(self):
        """
        dict: CSS colour names accepted by the legends, with their hexadecimal codes.
        """
        return CSS_COLORS
    def get_type(self,legendName) -> str:
        """
        Return the type of a legend.

        Args:
            legendName (str): name of the legend.

        Returns:
            str: ``"class"``, ``"range"``, ``"unique"`` or ``"continuous"``.

        Raises:
            Exception: if no legend has this name.
        """
        if legendName in self.get_list_name:
            return self.list_legend[legendName]['type']
        else:
            raise Exception('the given name does not correspond to a legend')
    def get_colorscheme_field(self,legendName) -> str:
        """
        Return the attribute fields a legend applies to.

        Args:
            legendName (str): name of the legend.

        Returns:
            list of str: the ``fieldToApply`` list of the legend.

        Raises:
            Exception: if no legend has this name.
        """
        if legendName in self.get_list_name:
            return self.list_legend[legendName]['field']
        else:
            raise Exception('the given name does not correspond to a legend')
    def get_colorschemeByName(self,name):
        """
        Return the colour scheme of a legend in the format used by ``TemporalMapViewer``.

        Args:
            name (str): name of the legend.

        Returns:
            dict or None: ``{'conditions': [...], 'choices': [...]}`` for ``class`` and
            ``range`` legends, ``None`` for the other types.

        Raises:
            Exception: if no legend has this name.
        """
        if name in self.list_legend.keys():
            if self.list_legend[name]['type']=='class':
                return self._createClassColorscheme(self.list_legend[name]['items'])
            elif self.list_legend[name]['type']=='range':
                return self._createRangeColorscheme(self.list_legend[name]['items'])
        else:
            raise Exception('the given name does not correspond to a legend')
    def get_colorscheme_for_plt(self, name=None, items=None, ltype=None):

        """
        Return a colour scheme in the format used by the plotting methods of ``Load``.

        Either give the name of a legend of the product, or give the legend items and
        type directly.

        Args:
            name (str, optional): name of a legend of the product.
            items (list or str, optional): legend items, used when ``name`` is not given.
            ltype (str, optional): legend type, used when ``name`` is not given.

        Returns:
            The colour scheme, depending on the legend type:

            - ``class``: dict ``{value: hexadecimal colour}``;
            - ``range``: list of tuples ``(valueMin, valueMax, hexadecimal colour)``;
            - ``unique``: a single hexadecimal colour;
            - ``continuous``: the items unchanged (colormap name);
            - ``None`` for an unknown type.

        Raises:
            ValueError: if neither ``name`` nor both ``items`` and ``ltype`` are given.
        """
        if name:
            legend = self.list_legend[name]
            ltype = legend["type"]
            items = legend["items"]

        # Case 2 : manual configuration
        elif items is None or ltype is None:
            raise ValueError(
                "Provide either a legend name OR both 'items' and 'ltype'."
            )

        if ltype == 'class':
            # {value: #hexcolor}
            return {element['value']: self._translateToHex(element['color']) for element in items}

        elif ltype == 'range':
            # list of tuples (min, max, #hexcolor)
            return [(element['valueMin'], element['valueMax'], self._translateToHex(element['color'])) for element in items]

        elif ltype == 'unique':
            # single fixed colour
            return self._translateToHex(items[0]['color'])

        elif ltype == 'continuous':
            # colormap name (string or list), e.g. 'YlOrRd'
            return items

        else:
            #raise ValueError(f"Unknown legend type: {ltype}")
            return None
    def get_legendFromColorscheme (self, name):
        """
        Return a legend in the format used by ipyleaflet ``LegendControl``.

        Args:
            name (str): name of the legend.

        Returns:
            dict: ``{'legend': {item name: hexadecimal colour}, 'title': str}``. The
            title is the legend ``title`` if defined, otherwise its name.
        """
        legend={}
        legend['legend']={element['name']:self._translateToHex(element['color']) for element in self.list_legend[name]['items']}
        legend['title']=self.list_legend[name].get('title',name)
        return legend
    def _translateToHex(self,color):
        #try:
        """
        Convert a colour to a hexadecimal code.

        Args:
            color (str, list or tuple): hexadecimal code (``"#fff"`` or ``"#ffffff"``),
                RGB triplet of integers between 0 and 255, or CSS colour name.

        Returns:
            str: hexadecimal colour code.

        Raises:
            Exception: if the colour is not valid.
        """
        if type(color)==str and re.match(r'^#[0-9abcdefABCDEF]{3}$|^#[0-9abcdefABCDEF]{6}$',color):
             return color 
        elif (type(color)==tuple or type(color)==list) and (len(color) == 3 and all(isinstance(x, int) and 0 <= x <= 255 for x in color)):
            hex_color = f'#{color[0]:02x}{color[1]:02x}{color[2]:02x}'
            return hex_color
        elif type(color)==str and re.match(r'^[a-zA-Z]+$',color) and color.lower() in CSS_COLORS.keys():
            return CSS_COLORS[color.lower()]
        else:
            raise Exception('Please provide a valid color name or code')

class TemporalMapViewer:
    """
    Interactive map with a time slider to visualise a time series of vector data.

    The features are reprojected to WGS84, simplified (tolerance of 0.0001 degree)
    and coloured according to a legend. The slider selects the date displayed on
    the map.

    Typical use with the output of ``Load``::

        legend = Legend(gdf.attrs['legend'])
        viewer = TemporalMapViewer(
            gdf=gdf, date_column='time', id_column='id',
            display_column=legend.get_colorscheme_field('niveau 1')[0],
            legendDict=legend.get_colorschemeByName('niveau 1'),
            legend=legend.get_legendFromColorscheme('niveau 1'))
        viewer.getSlider
        viewer.getMap
    """
    def __init__(self,
                 gdf,date_column,display_column,
                 legend:dict=None,
                 legendDict:str|dict =None,id_column='id',zoom=10):
        """
        Args:
            gdf (geopandas.GeoDataFrame): vector data to display, with one row per
                feature and date.
            date_column (str): name of the column holding the dates.
            display_column (str): name of the attribute used to colour the features.
            legend (dict, optional): legend to display on the map, as returned by
                ``Legend.get_legendFromColorscheme``.
            legendDict (dict or str, optional): colour scheme, either as returned by
                ``Legend.get_colorschemeByName`` or the name of a branca linear
                colormap (e.g. ``"YlOrRd_09"``). Without a valid colour scheme, all
                features are drawn in black.
            id_column (str): name of the column holding the feature identifiers.
            zoom (int): initial zoom level of the map.
        """
        self.gdf_copy=gdf.copy()
        self.date_column=date_column
        self.id_column=id_column
        self.zoom=zoom
        self.display_column=display_column
        self.currentLayer=None
        
        #convert into WGS84 if required
        if self.gdf_copy.crs and self.gdf_copy.crs.to_epsg() !=4326:
            self.gdf_copy=self.gdf_copy.to_crs('EPSG:4326')
        
        #create colorscheme
        #if pd.api.types.is_string_dtype(self.gdf_copy[self.display_column]):
        #    self.gdf_copy[self.display_column] = pd.to_numeric(self.gdf_copy[self.display_column], errors='coerce')
        #conditions = [
        #        (self.gdf_copy[self.display_column] >= 22) & (self.gdf_copy[self.display_column] <= 100),
        #        (self.gdf_copy[self.display_column] >= 102) & (self.gdf_copy[self.display_column] <= 360),
        #        (self.gdf_copy[self.display_column] >= 361)
        #    ]
        #choices = ["#13678A", "#45C4B0", "#9AEBA3"]
        #self.gdf_copy["colorscheme"] = np.select(conditions, choices, default="#DAFDBA")
        
        self._createLegend(legendDict)
        
        #simplifies the geom (if required need to create a function later) the tolerance unit will always be for wgs84
        self.gdf_copy['geometry'] = self.gdf_copy['geometry'].simplify(tolerance=0.0001, preserve_topology=True)
        
        #calculate center of the map
        bounds = self.gdf_copy.total_bounds
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2
        self.map_center = [center_lat, center_lon]
        self.boundsToFit=[[bounds[1],bounds[0]],[bounds[3],bounds[2]]]
        #change date into str if required
        if pd.api.types.is_datetime64_any_dtype(self.gdf_copy[self.date_column]):
            self.gdf_copy['time_str'] = self.gdf_copy[self.date_column].dt.strftime('%Y-%m-%d')
        else:
            self.gdf_copy['time_str'] = self.gdf_copy[self.date_column].astype(str)
        self.gdf_copy=self.gdf_copy.drop(self.date_column, axis=1)
        self.timeValues=sorted(self.gdf_copy['time_str'].unique())
        
        #create the map
        self.m=self._createMap(self.map_center,self.zoom)
        self.slider=self._createTimeSlider()
        self._updateMap(self.timeValues[0])
        if legend and ('legend' in legend.keys() and 'title' in legend.keys()):
            self.m.add(LegendControl(legend['legend'], title=legend['title'],position='topright'))
        
    @property
    def getMap(self):
        """
        ipyleaflet.Map: The map.
        """
        return self.m
    @property
    def getSlider(self):
        """
        ipywidgets.SelectionSlider: The time slider controlling the map.
        """
        return self.slider
    @property
    def getGdf(self):
        """
        geopandas.GeoDataFrame: The processed copy of the data (WGS84, simplified,
        with ``colorscheme`` and ``time_str`` columns).
        """
        return self.gdf_copy
    
    def _createMap(self,center,zoom):
        """
        Create the ipyleaflet map with an Esri World Topo basemap.
        """
        return Map(
            center=center,
            zoom = zoom,
            basemap= basemaps.Esri.WorldTopoMap)
    
    def _ensure_column_type_matches_condition(self,legendDict):
        """
        Convert the display column to the type of the legend values (string or numeric).
        """
        condition_value = legendDict['conditions'][0].__defaults__[0]
        column = self.gdf_copy[self.display_column]

        # Conversion to string if required
        if isinstance(condition_value, str) and not pd.api.types.is_string_dtype(column):
            self.gdf_copy = self.gdf_copy.astype({self.display_column: 'object'})

        # Conversion to numeric if required
        elif isinstance(condition_value, (int, float)) and not pd.api.types.is_numeric_dtype(column):
            self.gdf_copy[self.display_column] = pd.to_numeric(
                self.gdf_copy[self.display_column], 
                errors='coerce'
            )
    
    def _createLegend(self,legendDict,defaultColor='#fff'):
        """
        Compute the ``colorscheme`` column holding the colour of each feature.

        Args:
            legendDict (dict or str): colour scheme (conditions and choices) or name
                of a branca linear colormap.
            defaultColor (str): colour of the features that match no condition.
        """
        if type(legendDict)==dict and ('conditions' in legendDict.keys() and 'choices' in legendDict.keys()):
            self._ensure_column_type_matches_condition(legendDict)
            #conditions,choices,defaultColor=self._createChoicesAndConditions(legendDict)
            conditions=legendDict['conditions']
            choices=legendDict['choices']
            self.gdf_copy["colorscheme"] = np.select([func(self.gdf_copy, self.display_column) for func in conditions], choices, default=defaultColor)
        elif type(legendDict)==str and legendDict in dir(linear):
            cmap = getattr(linear,legendDict)
            cmap=cmap.scale(self.gdf_copy[self.display_column].min(),self.gdf_copy[self.display_column].max())
            self.gdf_copy['colorscheme']=self.gdf_copy.apply(lambda row: cmap(row[self.display_column]) if not math.isnan(row[self.display_column]) else None,axis=1)
        else:
            self.gdf_copy['colorscheme']=self.gdf_copy.apply(lambda row : '#000',axis=1)
        

    def _createTimeSlider(self):
        """
        Create the slider listing the available dates.
        """
        slider=widgets.SelectionSlider(
            options=self.timeValues,
            value=self.timeValues[0],
            description='Select date',
            disabled=False,
            continuous_update=False,
            orientation='horizontal',
            readout=True
        )
        slider.observe(self._onChangeSlider, names='value')
        return slider

    def _onChangeSlider(self, change):
        """
        Update the map when the slider date changes.
        """
        selected_date=change['new']
        self._updateMap(selected_date)
        
    def _click_function(self,**kwarg):
        """
        Callback for clicks on a feature. Does nothing for now.
        """
        
    def _style_function(self, feature):
        """
        Return the ipyleaflet style of a feature from its ``colorscheme`` property.
        """
        if feature['properties']['colorscheme']:
            return {
                'radius':5,
                'fillColor': feature['properties']['colorscheme'],
                'color': 'white',
                'weight':0,
                'fillOpacity': 0.8
            }
        else:
            return {
                'radius':5,
                'fillColor': 'white',
                'color': 'white',
                'weight': 1,
                'fillOpacity': 0.3
            }
    def _updateMap(self,date):
        """
        Replace the displayed layer by the features of the given date.

        Args:
            date (str): date to display, formatted as ``YYYY-MM-DD``.
        """
        if self.currentLayer and self.currentLayer in self.m.layers:
            self.m.remove(self.currentLayer)
        dataJson=json.loads(self.gdf_copy.loc[self.gdf_copy['time_str']==date][[self.display_column,'colorscheme','geometry']].to_json())
        self.currentLayer = GeoJSON(
            data=dataJson,
            style={'fillOpacity':1.0,'color':'white','weight':0},
            point_style={'radius': 5,'color': 'white','weight': 0,'fillOpacity': 0.8},
            style_callback=self._style_function,
            
            hover_style={'weight': 3, 'color': 'black'})
        self.currentLayer.on_click(self._click_function)
        self.m.add(self.currentLayer)
        self.m.fit_bounds(self.boundsToFit)