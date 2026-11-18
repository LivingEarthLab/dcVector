# This file is part of dcVector.
#
# Copyright (c) 2025-2026 Sébastien Chognard
# Copyright (c) 2025-2026 University of Geneva
# SPDX-License-Identifier: Apache-2.0
"""
Functions and classes to load and analyse vector data within the datacube.

This module provides:

- ``create_shape_geometry``: builds a Shapely geometry from various input
  formats and reprojects it, used to filter vector data spatially;
- ``Load``: loads raster and/or vector data from a single query, and plots or
  combines them (time-matched overlays, zonal statistics);
- ``create_linear_cmap``: builds a matplotlib colormap from values and colours.
"""
import json
import warnings
from typing import Union, List, Tuple, Dict, Any, Literal, Optional
import shapely
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
import numpy as np
import jsonschema
import datacube
from .forJupyter import Legend
from matplotlib import colormaps
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import pandas as pd
from affine import Affine
from rasterstats import zonal_stats
import pyproj
import re

import hvplot.xarray
import hvplot.pandas
import holoviews as hv
from holoviews import opts
hv.extension('bokeh')

class GeometryGenerator:
    """
    Build Shapely geometries from various input formats.

    Supported inputs are Shapely geometries, GeoJSON geometries, features and
    feature collections (with a single feature), JSON strings, dicts with
    ``geometry_type`` and ``coordinates`` or with ``x`` and ``y``, and arrays of
    coordinates.
    """
    
    def __init__(self):
        """
        Register the constructor of each supported geometry type.
        """
        self.geometry_types = {
            'point': self._create_point,
            'linestring': self._create_linestring,
            'polygon': self._create_polygon,
            'multipoint': self._create_multipoint,
            'multilinestring': self._create_multilinestring,
            'multipolygon': self._create_multipolygon
        }

    def create_geometry(self, data: Union[List, Dict, str, BaseGeometry]) -> BaseGeometry:
        """
        Create a Shapely geometry from the input data.

        Args:
            data (list, tuple, numpy.ndarray, dict, str or BaseGeometry): input data.
                A string is parsed as JSON. A Shapely geometry is returned unchanged.

        Returns:
            BaseGeometry: the Shapely geometry.

        Raises:
            ValueError: if the input format is not supported or the JSON is invalid.
        """
        # if it is already a shapely geom then return it
        if isinstance(data, BaseGeometry):
            return data

        # if it is a json parse it
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string")

        # Dict (GeoJSON or custom format)
        if isinstance(data, dict):
            return self._create_from_dict(data)

        # List of coordinates
        if isinstance(data, (list, tuple, np.ndarray)):
            return self._create_from_coordinates(data)

        raise ValueError(f"non supported format: {type(data)}")

    def _retrieve_geomType_and_coord_from_dict(self,geom_type:str,coordinates:list):

        """
        Create a geometry of the given type from its coordinates.

        Args:
            geom_type (str): geometry type in lower case (e.g. ``"polygon"``).
            coordinates (list): coordinates in the GeoJSON nesting for this type.

        Raises:
            ValueError: if the geometry type is not supported.
        """
        if geom_type in self.geometry_types:
            return self.geometry_types[geom_type](coordinates)
        else:
            raise ValueError(f"Unsupported geometry type: {geom_type}")

    def _create_from_dict(self, data: Dict[str, Any]) -> BaseGeometry:
        """
        Create a geometry from a dict.

        Accepted formats: GeoJSON geometry, dict with ``geometry_type`` and
        ``coordinates``, GeoJSON feature collection with a single feature, GeoJSON
        feature, or dict with ``x`` and ``y`` (point).

        Raises:
            ValueError: if the dict format is not recognised or if a feature
                collection holds more than one feature.
        """

        # Format GeoJSON
        if 'type' in data and 'coordinates' in data:
            return self._retrieve_geomType_and_coord_from_dict(data['type'].lower(),data['coordinates'])
        # Custom format with 'geometry_type' and 'coordinates'
        elif 'geometry_type' in data and 'coordinates' in data:
            return self._retrieve_geomType_and_coord_from_dict(data['geometry_type'].lower(),data['coordinates'])
        #format with features
        elif 'features' in data and len(data['features'])>0:
            if len(data['features'])==1:
                if 'geometry' in data['features'][0] and ('type' in data['features'][0]['geometry'] and 'coordinates' in data['features'][0]['geometry']):
                    return self._retrieve_geomType_and_coord_from_dict(data['features'][0]['geometry']['type'].lower(),data['features'][0]['geometry']['coordinates'])
            else:
                raise ValueError(f" {len(data['features'])} features were imported and only 1 was expected")
        elif 'geometry' in data and ('type' in data['geometry'] and 'coordinates' in data['geometry']):
            return self._retrieve_geomType_and_coord_from_dict(data['geometry']['type'].lower(),data['geometry']['coordinates'])
        # Dict holding the coordinates directly
        elif 'x' in data and 'y' in data:
            return Point(data['x'], data['y'])

        else:
            raise ValueError("Unrecognised dict format")

    def _create_from_coordinates(self, coordinates: Union[List, Tuple, np.ndarray]) -> BaseGeometry:
        """
        Create a geometry from an array of coordinates.

        - 1D array of 2 or 3 values (``[x, y]`` or ``[x, y, z]``): Point;
        - 1D array of 4 values (``[minX, minY, maxX, maxY]``): rectangle (Polygon);
        - 1D array of 6 values (``[minX, minY, minZ, maxX, maxY, maxZ]``): rectangle
          (Polygon) of the x/y bounds, the z bounds being ignored;
        - 2D array: Point (1 vertex), LineString (2 vertices or open line) or
          Polygon (3 vertices or more, first and last vertices equal);
        - 3D array: Polygon, the first ring being the exterior and the others holes.

        Raises:
            ValueError: if the coordinates format is not recognised.
        """
        coords = np.array(coordinates)

        # Single point [x, y] or [x, y, z]
        if coords.ndim == 1 and len(coords) in (2, 3):
            return Point(coords)

        # Bounding box [minX, minY, maxX, maxY] or [minX, minY, minZ, maxX, maxY, maxZ]
        elif coords.ndim == 1 and len(coords) in (4, 6):
            if len(coords) == 4:
                min_x, min_y, max_x, max_y = coords
            else:
                min_x, min_y, _, max_x, max_y, _ = coords
            if min_x >= max_x or min_y >= max_y:
                raise ValueError(f"Invalid bounding box: min values must be lower than max values ({coords.tolist()})")
            return box(min_x, min_y, max_x, max_y)

        # Several points or line
        elif coords.ndim == 2:
            if len(coords) == 1:
                # Single point
                return Point(coords[0])
            elif len(coords) == 2:
                # Two points -> LineString
                return LineString(coords)
            elif len(coords) >= 3:
                # Polygon if closed, otherwise LineString
                if np.allclose(coords[0], coords[-1]):
                    return Polygon(coords)
                else:
                    return LineString(coords)

        # Polygon with holes
        elif coords.ndim == 3:
            if len(coords) == 1:
                return Polygon(coords[0])
            else:
                # First ring = exterior, others = holes
                return Polygon(coords[0], coords[1:])

        raise ValueError("Unrecognised coordinates format")

    def _create_point(self, coordinates: List) -> Point:
        """
        Create a Point.
        """
        return Point(coordinates)

    def _create_linestring(self, coordinates: List) -> LineString:
        """
        Create a LineString.
        """
        return LineString(coordinates)

    def _create_polygon(self, coordinates: List) -> Polygon:
        """
        Create a Polygon (first ring exterior, other rings holes).
        """
        if len(coordinates) == 1:
            return Polygon(coordinates[0])
        else:
            return Polygon(coordinates[0], coordinates[1:])

    def _create_multipoint(self, coordinates: List) -> MultiPoint:
        """
        Create a MultiPoint.
        """
        return MultiPoint([Point(coord) for coord in coordinates])

    def _create_multilinestring(self, coordinates: List) -> MultiLineString:
        """
        Create a MultiLineString.
        """
        return MultiLineString([LineString(coord) for coord in coordinates])

    def _create_multipolygon(self, coordinates: List) -> MultiPolygon:
        """
        Create a MultiPolygon.
        """
        polygons = []
        for poly_coords in coordinates:
            if len(poly_coords) == 1:
                polygons.append(Polygon(poly_coords[0]))
            else:
                polygons.append(Polygon(poly_coords[0], poly_coords[1:]))
        return MultiPolygon(polygons)
    
    def extract_epsg_code(self,crs_input):
        """
        Extract the EPSG code from various CRS formats.

        Args:
            crs_input (int, str or pyproj.CRS): CRS as an EPSG code (``2154``,
                ``"2154"``, ``"EPSG:2154"``), any string understood by pyproj, or a
                pyproj CRS.

        Returns:
            int or None: the EPSG code, or ``None`` if it cannot be determined.
        """

        if isinstance(crs_input, int):
            return crs_input

        if isinstance(crs_input, str):
            # Format EPSG:xxxx
            if re.search(r'^(EPSG|epsg):([0-9]{4})$',crs_input):
                return int(re.search(r'^(EPSG|epsg):([0-9]{4})$',crs_input)[2])

            if crs_input.isdigit():
                return int(crs_input)

            try:
                crs = pyproj.CRS(crs_input)
                return crs.to_epsg()
            except:
                return None

        if isinstance(crs_input, pyproj.CRS):
            return crs_input.to_epsg()

        return None


def create_shape_geometry(data: Union[List, Dict, str, BaseGeometry],
                         geom_filter_crs,output_crs) -> BaseGeometry:
    """
    Create a Shapely geometry and reproject it to the output CRS.

    Used to build the spatial filter of a vector query.

    Args:
        data (list, dict, str or BaseGeometry): input geometry, in any format
            supported by ``GeometryGenerator.create_geometry``.
        geom_filter_crs (int, str or pyproj.CRS): CRS of the input geometry.
            EPSG:4326 is used if it cannot be determined.
        output_crs (int): EPSG code of the output CRS.

    Returns:
        BaseGeometry: the geometry in the output CRS.
    """
    generator = GeometryGenerator()
    epsg_geom_filter=generator.extract_epsg_code(geom_filter_crs) or 4326
    geom=shapely.set_srid(generator.create_geometry(data),epsg_geom_filter)
    if epsg_geom_filter != output_crs:
        transformer = pyproj.Transformer.from_crs("EPSG:"+str(epsg_geom_filter), "EPSG:"+str(output_crs), always_xy=True)
        return transform(transformer.transform, geom)
    else:
        return geom

class Load:
    
    """
    Load raster and/or vector data from the datacube with a single query.

    The vector data are loaded with ``Datacube.load_vect`` as a GeoDataFrame and
    the raster data with ``Datacube.load`` as an xarray Dataset. The class then
    provides plotting methods (matplotlib and holoviews), time-matched overlays of
    raster and vector data, and zonal statistics.

    The query is a dict with the following keys:

    - ``time`` (list of str): start and end dates;
    - ``product`` (str or dict): product name, or ``{'raster': name, 'vector': name}``
      to load both types;
    - ``crs``, ``output_crs`` (str): CRS of the query and of the output data;
    - ``resolution`` (number): raster resolution;
    - spatial extent (optional): ``x`` and ``y`` (ranges) or ``geopolygon`` for
      the raster data, ``spatialFilter`` (filter geometry, with its CRS in
      ``spatialFilter_crs``, EPSG:4326 by default) for the vector data;
    - ``ids`` (list, optional): identifiers of the vector features to load;
    - ``fields`` (list of str, optional): vector attributes to load;
    - ``measurements`` (list of str, optional): raster measurements to load
      (all by default);
    - ``dask_chunks`` (dict, optional): load the raster lazily with dask, e.g.
      ``{'x': 2048, 'y': 2048}``. Recommended for large rasters: each date is
      then only read when it is used.

    The query is checked against a JSON schema; an invalid query raises a warning
    but is still sent to the datacube.

    Example::

        query = {
            'time': ['2000-01-01', '2024-12-31'],
            'output_crs': 'epsg:2154',
            'product': {'raster': 'crop', 'vector': 'ocs'},
            'spatialFilter': geom,
            'spatialFilter_crs': 'epsg:4326',
        }
        results = Load(query)
    """
    def __init__(self,query):
        """
        Args:
            query (dict): query describing the data to load (see the class docstring).
        """
        self.schemaQuery={
          "$schema": "https://json-schema.org/draft/2020-12/schema",
          "type": "object",
          "properties": {
            "time": {
              "description": "time range to find and extract data",
              "type": "array",
              "items": {"type": "string"}
            },
            "crs": {"type": "string"},
            "output_crs": {"type": "string"},
            "resolution": {"type": "number"},
            "measurements": {"type": "array", "items": {"type": "string"}},
            "dask_chunks": {"type": "object"},
            "product": {
              "oneOf": [
                {"type": "string"},
                {"type": "object","properties": {"raster": {"type": "string"},"vector": {"type": "string"}}}]},
            "spatialFilter_crs":{
                "oneOf":[
                    {"type":"string"},
                    {"type":"number"}
                ]
            },
            "spatialFilter": {"$ref": "#/definitions/spatialFilter"},
            "x": {"type": "array","prefixItems": [{"type": "number"},{"type": "number"}],"items": False,"minItems": 2,"maxItems": 2},
            "y": {"type": "array","prefixItems": [{"type": "number"},{"type": "number"}],"items": False,"minItems": 2,"maxItems": 2},
            "geopolygon": {"type": "string"},
            "fields": {
              "type": "array",
              "items": {"type": "string"}
            },
            "ids": {
                "type": "array",
                "oneOf": [
                    {"items": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "number"}
                        ]}
                    },
                    {
                        "items": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "prefixItems": [
                                {
                                    "oneOf": [
                                        {"type": "string"},
                                        {"type": "number"},
                                        {
                                            "type": "array",
                                            "items": {
                                                "oneOf": [
                                                    {"type": "string"},
                                                    {"type": "number"}
                                                ]
                                            }
                                        }
                                    ]
                                },
                                {
                                    # Second element: date (string) or number
                                    "oneOf": [
                                        {"type": "string"},
                                        {"type": "number"}
                                    ]
                                }
                            ]
                        }
                    }
                ]
            }
          },
          "required": ["time", "product"],
          "definitions": {
            "spatialFilter": {
              "anyOf": [
                {
                  "title": "Simple coordinates - Point",
                  "type": "array",
                  "items": {"type": "number"},
                  "minItems": 2,
                  "maxItems": 3,
                  "description": "Format: [longitude, latitude] or [x, y, z]"
                },
                {
                  "title": "Bbox - Bounding Box",
                  "type": "array",
                  "items": {"type": "number"},
                  "minItems": 4,
                  "maxItems": 6,
                  "description": "Format: [minX, minY, maxX, maxY] or [minX, minY, minZ, maxX, maxY, maxZ]"
                },
                {
                  "title": "GeoJSON Geometry",
                  "type": "object",
                  "required": ["type", "coordinates"],
                  "properties": {
                    "type": {
                      "type": "string",
                      "enum": ["Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon", "GeometryCollection"]
                    },
                    "coordinates": {
                      "oneOf": [
                        {
                          "type": "array",
                          "items": {"type": "number"}
                        },
                        {
                          "type": "array",
                          "items": {
                            "type": "array",
                            "items": {"type": "number"}
                          }
                        },
                        {
                          "type": "array",
                          "items": {
                            "type": "array",
                            "items": {
                              "type": "array",
                              "items": {"type": "number"}
                            }
                          }
                        },
                        {
                          "type": "array",
                          "items": {
                            "type": "array",
                            "items": {
                              "type": "array",
                              "items": {
                                "type": "array",
                                "items": {"type": "number"}
                              }
                            }
                          }
                        }
                      ]
                    },
                    "geometries": {
                      "type": "array",
                      "items": {"$ref": "#/definitions/geoJsonGeometry"}
                    }
                  },
                  "allOf": [
                    {
                      "if": {
                        "properties": {"type": {"const": "GeometryCollection"}}
                      },
                      "then": {
                        "required": ["geometries"],
                        "not": {"required": ["coordinates"]}
                      },
                      "else": {
                        "required": ["coordinates"],
                        "not": {"required": ["geometries"]}
                      }
                    }
                  ]
                },
                {
                  "title": "GeoJSON Feature",
                  "type": "object",
                  "required": ["type", "geometry"],
                  "properties": {
                    "type": {"const": "Feature"},
                    "geometry": {"$ref": "#/definitions/geoJsonGeometry"},
                    "properties": {
                      "type": "object",
                      "additionalProperties": True
                    }
                  }
                },
                {
                  "title": "GeoJSON FeatureCollection",
                  "type": "object",
                  "required": ["type", "features"],
                  "properties": {
                    "type": {"const": "FeatureCollection"},
                    "features": {
                      "type": "array",
                      "items": {"$ref": "#/definitions/geoJsonFeature"}
                    }
                  }
                },
                {
                  "title": "WKT String",
                  "type": "string",
                  "pattern": "^(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON|GEOMETRYCOLLECTION)\\s*\\(",
                  "description": "Well-Known Text format: POINT(1 2), POLYGON((0 0, 1 0, 1 1, 0 1, 0 0)), etc."
                },
                {
                  "title": "Shapely-like dict",
                  "type": "object",
                  "properties": {
                    "__geo_interface__": {"$ref": "#/definitions/geoJsonGeometry"},
                    "geom_type": {
                      "type": "string",
                      "enum": ["Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon", "GeometryCollection"]
                    },
                    "coords": {
                      "type": "array",
                      "items": {"type": "number"}
                    },
                    "bounds": {
                      "type": "array",
                      "items": {"type": "number"},
                      "minItems": 4,
                      "maxItems": 4
                    }
                  },
                  "additionalProperties": True
                },
                {
                  "title": "List of coordinates",
                  "type": "array",
                  "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2
                  },
                  "minItems": 2,
                  "description": "Format: [[x1, y1], [x2, y2], ...] defining a polygon or a line"
                }
              ]
            },
            "geoJsonGeometry": {
              "type": "object",
              "required": ["type", "coordinates"],
              "properties": {
                "type": {
                  "type": "string",
                  "enum": ["Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon", "GeometryCollection"]
                },
                "coordinates": {
                  "oneOf": [
                    {
                      "type": "array",
                      "items": {"type": "number"}
                    },
                    {
                      "type": "array",
                      "items": {
                        "type": "array",
                        "items": {"type": "number"}
                      }
                    },
                    {
                      "type": "array",
                      "items": {
                        "type": "array",
                        "items": {
                          "type": "array",
                          "items": {"type": "number"}
                        }
                      }
                    }
                  ]
                },
                "geometries": {
                  "type": "array",
                  "items": {"$ref": "#/definitions/geoJsonGeometry"}
                }
              },
              "allOf": [
                {
                  "if": {
                    "properties": {"type": {"const": "GeometryCollection"}}
                  },
                  "then": {
                    "required": ["geometries"],
                    "not": {"required": ["coordinates"]}
                  },
                  "else": {
                    "required": ["coordinates"],
                    "not": {"required": ["geometries"]}
                  }
                }
              ]
            },
            "geoJsonFeature": {
              "type": "object",
              "required": ["type", "geometry"],
              "properties": {
                "type": {"const": "Feature"},
                "geometry": {"$ref": "#/definitions/geoJsonGeometry"},
                "properties": {
                  "type": "object",
                  "additionalProperties": True
                }
              }
            }
          }
        }
        try:
            jsonschema.validate(instance=query, schema=self.schemaQuery)
        except jsonschema.exceptions.ValidationError as e:
            warnings.warn(f"The query is invalid: {e.message}")
        self.query=query
        self.query_for_vect = {k: v for k, v in self.query.items() if k in ['time', 'output_crs', 'spatialFilter','spatialFilter_crs',"ids","fields"]}
        self.dc=datacube.Datacube(app='Load class')
        self.productVector=self._get_product(self.query,"vector")
        self.query_for_raster = {k: v for k, v in self.query.items() if k in ['time', 'output_crs', 'crs',"resolution","x","y","geopolygon","measurements","dask_chunks"]}
        self.productRaster=self._get_product(self.query,"raster")
        self.data_vector=self.dc.load_vect(product=self.productVector,**self.query_for_vect) if self.productVector else None
        self.data_raster=self.dc.load(product=self.productRaster,**self.query_for_raster) if self.productRaster else None
        self.default_legend=Legend(self.data_vector.attrs['legend']) if self.productVector else None
        self.nodata_value=self.dc.list_measurements().loc[self.productRaster].get('nodata',None).iloc[0] if self.productRaster else None
        self.vect_crs=pyproj.CRS(self.data_vector.crs.to_epsg()) if (
            self.data_vector is not None 
            and not self.data_vector.empty
            and self.data_vector.crs is not None) else None
        self.rast_crs = pyproj.CRS(self.data_raster.crs) if self.data_raster is not None else None
    def _get_product(self,query: dict,typeProduct:Literal["raster","vector"]) -> Optional[str]:
        """
        Return the product name of the given type from the query.

        Args:
            query (dict): the query.
            typeProduct (str): ``"raster"`` or ``"vector"``.

        Returns:
            str or None: the product name if it exists in the index for this type,
            otherwise ``None``.
        """
        product = query.get('product')

        # Extraction of the value
        product_name = (
            product.get(typeProduct) if isinstance(product, dict) else product if isinstance(product, str) else None
        )

        # Validation
        if not product_name:
            return None
        available = {
            "raster": set(self.dc.list_measurements().index.get_level_values(0)),
            "vector": set(self.dc.list_attributes().index.get_level_values(0))}
        return product_name if product_name in available[typeProduct] else None
    
    @property
    def get_raster_dataset(self):
        """
        xarray.Dataset or None: The loaded raster data.
        """
        return self.data_raster

    @property
    def get_vector_dataset(self):
        """
        geopandas.GeoDataFrame or None: The loaded vector data. Its ``attrs['legend']``
        attribute holds the legends of the product.
        """
        return self.data_vector
    
    def _validate_colorscheme(self, colorscheme):
        """
        Return the colormap if valid (matplotlib colormap or registered name), otherwise ``"viridis"``.
        """
        if isinstance(colorscheme, LinearSegmentedColormap):
            return colorscheme

        if isinstance(colorscheme, str):
            return colorscheme if colorscheme in list(colormaps) else 'viridis'

        return 'viridis'

    def _trans_bounds(self,bounds):
        """
        Reproject bounds ``[minx, miny, maxx, maxy]`` from the vector CRS to the raster CRS.
        """
        tr=pyproj.Transformer.from_crs(self.vect_crs,self.rast_crs,always_xy=True)
        coords_init = [(bounds[0], bounds[1]), (bounds[2], bounds[3])]
        coords_trans = [tr.transform(x, y) for x, y in coords_init]
        return [coord for pair in coords_trans for coord in pair]

    def _plot_vector_subset(self, subset, ax, field, ltype, colorSchemePlt):
        """
        Plot a subset of the vector data with matplotlib, according to the legend type.

        Args:
            subset (geopandas.GeoDataFrame): features to plot.
            ax (matplotlib.axes.Axes): axes to plot on.
            field (str): attribute used to colour the features.
            ltype (str): legend type (``class``, ``range``, ``unique`` or ``continuous``).
            colorSchemePlt: colour scheme as returned by ``Legend.get_colorscheme_for_plt``.
        """
        if ltype == 'class':
            for code, data in subset.groupby(field):
                data.plot(ax=ax, color=colorSchemePlt.get(code, "white"))

        elif ltype == 'range':
            def get_range_color(value):
                for vmin, vmax, color in colorSchemePlt:
                    if vmin <= value <= vmax:
                        return color
                return "white"
            subset = subset.copy()
            subset['_color'] = subset[field].apply(get_range_color)
            subset.plot(ax=ax, color=subset['_color'])

        elif ltype == 'unique':
            subset.plot(ax=ax, color=colorSchemePlt)

        elif ltype == 'continuous':
            subset.plot(ax=ax, column=field, cmap=colorSchemePlt[0].get('codeName', 'viridis'))

    def _compute_row_number(self, time_step, column_number):
        """
        Return the number of subplot rows needed for ``time_step`` plots on ``column_number`` columns.
        """
        return int(time_step/column_number)+1 if time_step%column_number > 0 else int(time_step/column_number)

    def _plot_raster_subset(self, ax, data_masked, val, colorscheme):
        """
        Plot the raster slice of a given date with matplotlib, using the global min/max as colour range.
        """
        data_masked.sel(time=val).plot(
            ax=ax,
            vmin=data_masked.min(),
            vmax=data_masked.max(),
            cmap=colorscheme,
            add_colorbar=False
        )

    def _build_overlay_title(self, dates_to_run, i, val, ax, data_vect_temp, field, ltype, colorSchemePlt):
        """
        Overlay the matched vector data on a raster subplot and return its title.

        Returns:
            str: title giving the raster date and the matched vector date (or ``None``).
        """
        title_text = "raster date: " + pd.to_datetime(str(val)).strftime('%Y-%m-%d') + "\n"
        vector_val = dates_to_run.iloc[i]["vector"]
        if vector_val is not pd.NaT and not pd.isnull(vector_val):
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            subset = data_vect_temp[data_vect_temp['time'] == dates_to_run['vector'].iloc[i]]
            self._plot_vector_subset(subset, ax, field, ltype, colorSchemePlt)
            ax.set_xlim(xlim)
            ax.set_ylim(ylim)
            title_text += "vector date: " + pd.to_datetime(str(dates_to_run['vector'].iloc[i])).strftime('%Y-%m-%d')
        else:
            title_text += "vector date: None"
        return title_text

    def vector_subplot(self,legend_name,column_number=3):
        """
        Plot the vector time series with matplotlib, one subplot per date.

        Args:
            legend_name (str): name of the product legend used to colour the features.
            column_number (int): number of subplot columns.

        Returns:
            tuple: ``(axes, fig)``, where ``axes`` is a 2D array of axes (or a single
            axes if there is only one date) and ``fig`` the matplotlib figure.

        Raises:
            ValueError: if no vector data were loaded.
        """
        if self.data_vector is None:
            raise ValueError(f"No vector data were retrieved with the query provided")
        time_step=len(set(self.data_vector['time']))
        row_number = int(time_step/column_number)+1 if time_step%column_number >0 else int(time_step/column_number)
        colorSchemePlt=self.default_legend.get_colorscheme_for_plt(legend_name)
        ltype = self.default_legend.get_type(legend_name)
        field=self.default_legend.get_colorscheme_field(legend_name)[0]
        time_values = sorted(set(self.data_vector['time']))

        if time_step > 1:
            fig, axes = plt.subplots(nrows=row_number, ncols=column_number, sharex=True)
            ax2d = np.array(axes).reshape(row_number, column_number)
            for axis in ax2d.flat:
                axis.axis('off')
            for i, val in enumerate(time_values):
                current_ax = ax2d[i // column_number, i % column_number]
                subset = self.data_vector[self.data_vector['time'] == val]
                self._plot_vector_subset(subset, current_ax, field, ltype, colorSchemePlt)
                current_ax.set_title(val.strftime('%Y-%m-%d'))
            return ax2d, fig
        else:
            fig, ax = plt.subplots()
            ax.axis('off')
            self._plot_vector_subset(self.data_vector, ax, field, ltype, colorSchemePlt)
            ax.set_title(time_values[0].strftime('%Y-%m-%d')) 
            return ax,fig


    def raster_subplot(self, name_dataset, colorscheme='viridis', cut_to_vector_extent=False, column_number=3):
        """
        Plot the raster time series with matplotlib, one subplot per date.

        No-data values are masked.

        Args:
            name_dataset (str): name of the raster measurement to plot.
            colorscheme (str or LinearSegmentedColormap): matplotlib colormap.
                ``"viridis"`` is used if it is not valid.
            cut_to_vector_extent (bool): clip the raster to the extent of the vector data.
            column_number (int): number of subplot columns.

        Returns:
            tuple: ``(axes, fig)``, where ``axes`` is a 2D array of axes (or a single
            axes if there is only one date) and ``fig`` the matplotlib figure.

        Raises:
            ValueError: if no raster data were loaded.
        """
        if self.data_raster is None:
            raise ValueError(f"No raster data were retrieved with the query provided")
        data_raster_temp = self.get_raster_clip_to_vectors_bounds if cut_to_vector_extent else self.data_raster
        time_step = len(data_raster_temp.time.values)
        row_number = self._compute_row_number(time_step, column_number)
        colorscheme = self._validate_colorscheme(colorscheme)
        data_masked = data_raster_temp[name_dataset].where(data_raster_temp[name_dataset] != self.nodata_value)

        if time_step > 1:
            fig, axes = plt.subplots(nrows=row_number, ncols=column_number, sharex=True)
            ax2d = np.array(axes).reshape(row_number, column_number)
            for axis in ax2d.flat:
                axis.axis('off')
            for i, val in enumerate(data_raster_temp.time.values):
                current_ax = ax2d[i // column_number, i % column_number]
                self._plot_raster_subset(current_ax, data_masked, val, colorscheme)
                current_ax.set_title(pd.to_datetime(str(val)).strftime('%Y-%m-%d'))
            return ax2d, fig
        else:
            fig, ax = plt.subplots()
            ax.axis('off')
            self._plot_raster_subset(ax, data_masked, data_raster_temp.time.values[0], colorscheme)
            ax.set_title(pd.to_datetime(str(data_raster_temp.time.values[0])).strftime('%Y-%m-%d'))
            return ax, fig
        
    def raster_vector_subplot(self, legend_name, name_dataset, colorscheme='viridis',
                               cut_to_vector_extent=False, extrapolation=None,
                               time_range='D', column_number=3):
        """
        Plot each raster date with the matching vector data overlaid (matplotlib).

        For each raster date, the matching vector date is the latest vector date
        before or equal to it, kept if it falls in the same period as defined by
        ``time_range``, or in any case if extrapolation is enabled.

        Args:
            legend_name (str): name of the product legend used to colour the features.
            name_dataset (str): name of the raster measurement to plot.
            colorscheme (str or LinearSegmentedColormap): matplotlib colormap of the raster.
            cut_to_vector_extent (bool): clip the raster to the extent of the vector data.
            extrapolation (bool, optional): use the latest earlier vector date whatever
                the period. Defaults to the ``extrapolation`` value of the product metadata.
            time_range (str): period used to match the dates: ``"Y"``, ``"M"``,
                ``"D"``, ``"h"``, ``"m"`` or ``"s"``.
            column_number (int): number of subplot columns.

        Returns:
            tuple: ``(axes, fig)``.

        Raises:
            ValueError: if raster or vector data are missing, or if the raster only
                holds no-data values.
        """
        if (self.data_raster is None) or (self.data_vector is None):
            missing = []
            if self.data_raster is None: missing.append("raster")
            if self.data_vector is None: missing.append("vector")
            raise ValueError(f"No {' and '.join(missing)} data were retrieved with the query provided")

        time_val_raster = self.data_raster.indexes['time'].values
        time_val_vect = np.unique(self.data_vector['time'])
        datasets = self.dc.find_datasets(product=self.productVector, **{'time': self.query_for_vect.get('time')})
        ds, *_ = datasets
        extrapolation_value = extrapolation if extrapolation is not None else ds.product.lookup_attributes().get(list(ds.product.lookup_attributes().keys())[0]).get('extrapolation', False)
        dates_to_run = self._create_time_extrapolation(time_val_raster, time_val_vect, time_range, extrapolation_value)
        data_raster_temp = self.get_raster_clip_to_vectors_bounds if cut_to_vector_extent else self.data_raster
        data_vect_temp = self.data_vector if self.rast_crs == self.vect_crs else self.data_vector.to_crs(self.rast_crs)
        colorSchemePlt = self.default_legend.get_colorscheme_for_plt(name=legend_name)
        ltype = self.default_legend.get_type(legend_name)
        field = self.default_legend.get_colorscheme_field(legend_name)[0]
        data_masked = data_raster_temp[name_dataset].where(data_raster_temp[name_dataset] != self.nodata_value)
        if np.isnan(data_masked).all():
            raise ValueError("raster only composed of no data values")

        time_step = len(dates_to_run['raster'])
        row_number = self._compute_row_number(time_step, column_number)

        if time_step > 1:
            fig, axes = plt.subplots(nrows=row_number, ncols=column_number, sharex=True)
            ax2d = np.array(axes).reshape(row_number, column_number)
            for axis in ax2d.flat:
                axis.axis('off')
            for i, val in enumerate(dates_to_run['raster']):
                current_ax = ax2d[i // column_number, i % column_number]
                self._plot_raster_subset(current_ax, data_masked, val, colorscheme)
                current_ax.set_aspect('auto')
                title_text = self._build_overlay_title(dates_to_run, i, val, current_ax, data_vect_temp, field, ltype, colorSchemePlt)
                current_ax.set_aspect('auto')
                current_ax.set_title(title_text, size=8)
            return ax2d, fig
        else:
            fig, ax = plt.subplots()
            ax.axis('off')
            self._plot_raster_subset(ax, data_masked, dates_to_run['raster'].iloc[0], colorscheme)
            title_text = self._build_overlay_title(dates_to_run, 0, dates_to_run['raster'].iloc[0], ax, data_vect_temp, field, ltype, colorSchemePlt)
            ax.set_title(title_text, size=8)
            return ax, fig

    @property
    def get_raster_clip_to_vectors_bounds(self):
        """
        xarray.Dataset: The raster data clipped to the bounding box of the vector data.

        Raises:
            ValueError: if raster or vector data are missing.
        """
        if (self.data_raster is None) or (self.data_vector is None):
            missing = []
            if self.data_raster is None:
                missing.append("raster")
            if self.data_vector is None:
                missing.append("vector")
            data_type = " and ".join(missing)
            raise ValueError(f"No {data_type} data were retrieved with the query provided")
        vect_bounds=(
            self.data_vector.total_bounds if pyproj.CRS(self.data_raster.crs)==pyproj.CRS(self.data_vector.crs.to_epsg()) 
            else self._trans_bounds(self.data_vector.total_bounds))
        return self.data_raster.sel(
            x=slice(vect_bounds[0], vect_bounds[2]),
            y=slice(vect_bounds[3],vect_bounds[1])
        )

    def _getAffine(self,data_raster):
        """
        Return the affine transform of a raster from its x and y coordinates (pixel centres).
        """
        x_coords = data_raster.x.values
        y_coords = data_raster.y.values
        x_res = x_coords[1] - x_coords[0]  
        y_res = y_coords[1] - y_coords[0]
        x_min = x_coords[0] - x_res / 2
        y_max = y_coords[0] - y_res / 2
        return Affine(x_res, 0.0, x_min, 
                           0.0, y_res, y_max)
    def _raster_stat(self,raster_vect_copy,raster_variable,time_raster_val,time_vector_val,stats_to_implement):
        """
        Compute zonal statistics of one raster date over the vector features of one date.

        Returns:
            geopandas.GeoDataFrame: the features of the vector date with one column per
            statistic and a ``date_raster_stat`` column.
        """
        subset = raster_vect_copy[raster_vect_copy['time'] == time_vector_val].copy()
        transform = self._getAffine(self.data_raster)
        raster_data = self.data_raster[raster_variable].sel(time=time_raster_val).values
        # Zonal statistics, returned in the order of the features
        stats_res = zonal_stats(
            subset.geometry,
            raster_data,
            affine=transform,
            stats=stats_to_implement,
            nodata=self.nodata_value,
            all_touched=True
        )
        del raster_data
        # Results assigned in one step, by position (robust to a non-unique index)
        stats_df = pd.DataFrame(stats_res)
        subset = subset.assign(**{col: stats_df[col].to_numpy() for col in stats_df.columns})
        subset['date_raster_stat'] = pd.Timestamp(time_raster_val)
        return subset

    # Statistics of the pixels of a single class, derived from their count:
    # all the pixels have the value of the class.
    _CLASS_STATS_FROM_VALUE = ('mean', 'min', 'max', 'median', 'majority', 'minority')
    _CLASS_STATS_ZERO = ('std', 'range')

    def _raster_stat_by_class(self, raster_vect_copy, raster_variable, time_raster_val, time_vector_val, stats_to_implement):
        """
        Compute zonal statistics separately for each raster class.

        The number of pixels of each class in each feature is computed in a single
        pass with the ``categorical`` mode of rasterstats. The other statistics are
        derived from it, since all the pixels of a class have the same value:
        ``sum`` = count × class value; ``mean``, ``min``, ``max``, ``median``,
        ``majority``, ``minority`` = class value; ``std``, ``range`` = 0; ``unique`` = 1.
        They are NaN for a feature without pixels of the class. The columns are
        named ``<stat>_class_<value>``, one per class found in the raster date.

        Returns:
            geopandas.GeoDataFrame: the features of the vector date with the
            statistics of each class.

        Raises:
            ValueError: if a statistic cannot be computed by class.
        """
        supported = ('count', 'sum', 'unique') + self._CLASS_STATS_FROM_VALUE + self._CLASS_STATS_ZERO
        unsupported = [s for s in stats_to_implement if s not in supported]
        if unsupported:
            raise ValueError(f"Statistics not available with by_class=True: {unsupported}. Available: {list(supported)}")

        subset = raster_vect_copy[raster_vect_copy['time'] == time_vector_val].copy()
        transform = self._getAffine(self.data_raster)
        raster_data = self.data_raster[raster_variable].sel(time=time_raster_val).values

        # Unique classes of the raster (excluding nodata). For non-negative integer
        # rasters (e.g. uint8 land cover maps), bincount avoids copying and sorting the array.
        if np.issubdtype(raster_data.dtype, np.integer) and raster_data.size and raster_data.min() >= 0:
            unique_classes = np.nonzero(np.bincount(raster_data.ravel()))[0].astype(raster_data.dtype)
            unique_classes = unique_classes[unique_classes != self.nodata_value]
        else:
            unique_classes = np.unique(raster_data[raster_data != self.nodata_value])

        # Number of pixels of each class in each feature, in a single pass
        categories = zonal_stats(
            subset.geometry,
            raster_data,
            affine=transform,
            categorical=True,
            nodata=self.nodata_value,
            all_touched=True
        )
        del raster_data
        counts = pd.DataFrame(categories)
        counts.columns = [c.item() if hasattr(c, 'item') else c for c in counts.columns]

        new_columns = {}
        for cls in unique_classes:
            cls_value = cls.item()
            n = counts[cls_value].fillna(0).to_numpy(dtype=float) if cls_value in counts.columns else np.zeros(len(subset))
            present = n > 0
            for stat in stats_to_implement:
                if stat == 'count':
                    values = n
                elif stat == 'sum':
                    values = np.where(present, n * cls_value, np.nan)
                elif stat == 'unique':
                    values = np.where(present, 1.0, np.nan)
                elif stat in self._CLASS_STATS_FROM_VALUE:
                    values = np.where(present, float(cls_value), np.nan)
                else:
                    values = np.where(present, 0.0, np.nan)
                new_columns[f"{stat}_class_{cls}"] = values

        # Results assigned in one step, by position (robust to a non-unique index)
        subset = subset.assign(**new_columns)
        subset['date_raster_stat'] = pd.Timestamp(time_raster_val)
        return subset

    def dc_zonal_stat(self,
                      raster_variable,
                      time_range='D',
                      stats_to_implement=['mean', 'std', 'min', 'max', 'count', 'sum'],
                      extrapolation=None,
                      by_class=False
                     ):
        """
        Compute zonal statistics of the raster over the vector features, for each matched date.

        Raster and vector dates are matched as in ``raster_vector_subplot``.

        Args:
            raster_variable (str): name of the raster measurement.
            time_range (str): period used to match the dates: ``"Y"``, ``"M"``,
                ``"D"``, ``"h"``, ``"m"`` or ``"s"``.
            stats_to_implement (list of str): statistics computed by rasterstats
                (e.g. ``mean``, ``std``, ``min``, ``max``, ``count``, ``sum``).
            extrapolation (bool, optional): use the latest earlier vector date whatever
                the period. Defaults to the ``extrapolation`` value of the product metadata.
            by_class (bool): compute the statistics separately for each raster class
                (see ``_raster_stat_by_class``). Available statistics: ``count``,
                ``sum``, ``mean``, ``min``, ``max``, ``median``, ``majority``,
                ``minority``, ``std``, ``range``, ``unique``.

        Returns:
            pandas.DataFrame: the vector features with the statistics and the raster
            date used (``date_raster_stat``). Raster dates without a matching
            vector date are skipped; the result is empty if no date matches.

        Raises:
            ValueError: if raster or vector data are missing.
        """
        if (self.data_raster is None) or ( self.data_vector is None):
            missing = []
            if self.data_raster is None:
                missing.append("raster")
            if self.data_vector is None:
                missing.append("vector")
            data_type = " and ".join(missing)
            raise ValueError(f"No {data_type} data were retrieved with the query provided")
        time_val_raster = self.data_raster.indexes['time'].values
        time_val_vect = np.unique(self.data_vector['time'])
        datasets = self.dc.find_datasets(product=self.productVector, **{'time': self.query_for_vect.get('time')})
        ds, *_ = datasets
        extrapolation_value = extrapolation if extrapolation is not None else ds.product.lookup_attributes().get(
            list(ds.product.lookup_attributes().keys())[0]).get('extrapolation', False)
        dates_to_run = self._create_time_extrapolation(time_val_raster, time_val_vect, time_range, extrapolation_value)
        data_vector_stat = self.data_vector.copy()
        data_vector_stat['date_raster_stat'] = pd.NaT
        results = []
        for i in dates_to_run.index:
            vector_date = dates_to_run.iloc[i]["vector"]
            if pd.isna(vector_date):
                continue
            raster_date = dates_to_run.iloc[i]["raster"]
            compute = self._raster_stat_by_class if by_class else self._raster_stat
            results.append(compute(data_vector_stat, raster_variable, raster_date, vector_date, stats_to_implement))
        if not results:
            return data_vector_stat.iloc[0:0]
        return pd.concat(results)

    def _create_time_extrapolation(self,time_val_raster, time_val_vect,time_range,extrapolation=False):
        """
        Match each raster date with a vector date.

        The candidate vector date is the latest one before or equal to the raster
        date. It is kept if extrapolation is enabled, or if both dates fall in the same
        period at the ``time_range`` precision; otherwise the vector date is ``NaT``.

        Returns:
            pandas.DataFrame: columns ``raster`` and ``vector`` with the matched dates.
        """
        data_rows = []
        for element in time_val_raster:
            if len(time_val_vect [time_val_vect <= element])>0:
                time_select=time_val_vect [time_val_vect <= element][-1]
                if extrapolation:
                    data_rows.append([element, time_select])
                elif (time_range == 'Y') and (element.astype('datetime64[Y]').astype(int)==time_select.astype('datetime64[Y]').astype(int)):
                    data_rows.append([element, time_select])
                elif (time_range == 'M') and (element.astype('datetime64[M]').astype(int)==time_select.astype('datetime64[M]').astype(int)):
                    data_rows.append([element, time_select])
                elif (time_range == 'D') and (element.astype('datetime64[D]').astype(int)==time_select.astype('datetime64[D]').astype(int)):
                    data_rows.append([element, time_select])
                elif (time_range == 'h') and (element.astype('datetime64[h]').astype(int)==time_select.astype('datetime64[h]').astype(int)):
                    data_rows.append([element, time_select])
                elif (time_range == 'm') and (element.astype('datetime64[m]').astype(int)==time_select.astype('datetime64[m]').astype(int)):
                    data_rows.append([element, time_select])
                elif (time_range == 's') and (element.astype('datetime64[s]').astype(int)==time_select.astype('datetime64[s]').astype(int)):
                    data_rows.append([element, time_select])
                else:
                    data_rows.append([element, pd.NaT])
            else:
                data_rows.append([element, pd.NaT])
        results=pd.DataFrame(data_rows, columns=['raster', 'vector'])
        return results.astype({'raster': 'datetime64[s]', 'vector': 'datetime64[s]'})
    def _hvplot_vector_subset(self, subset, field, ltype, colorSchemePlt, width=400, height=400):
        """
        Plot a subset of the vector data with hvplot, according to the legend type.

        Returns:
            holoviews element: the plot.
        """
        if ltype == 'class':
            subset = subset.copy()
            subset['_color'] = subset[field].map(lambda c: colorSchemePlt.get(c, "white"))
            return subset.hvplot(
                geo=False, color='_color', width=width, height=height,
                line_width=0, hover_cols=[field]
            ).opts(xaxis=None, yaxis=None)
        elif ltype == 'range':
            def get_range_color(value):
                for vmin, vmax, color in colorSchemePlt:
                    if vmin <= value <= vmax:
                        return color
                return "white"
            subset = subset.copy()
            subset['_color'] = subset[field].apply(get_range_color)
            return subset.hvplot(
                geo=False, color='_color', width=width, height=height,
                line_width=0, hover_cols=[field]
            ).opts(xaxis=None, yaxis=None)
        elif ltype == 'unique':
            return subset.hvplot(
                geo=False, color=colorSchemePlt, width=width, height=height, line_width=0
            ).opts(xaxis=None, yaxis=None)
        elif ltype == 'continuous':
            return subset.hvplot(
                geo=False, c=field, cmap=colorSchemePlt[0].get('codeName', 'viridis'),
                width=width, height=height, line_width=0
            ).opts(xaxis=None, yaxis=None)

    def _hvplot_raster_subset(self, data_masked, val, colorscheme, width=400, height=400):
        """
        Plot the raster slice of a given date with hvplot, using the global min/max as colour range.
        """
        return data_masked.sel(time=val).hvplot(
            cmap=colorscheme,
            clim=(float(data_masked.min()), float(data_masked.max())),
            width=width, height=height,
            colorbar=False,
            hover=True
        ).opts(xaxis=None, yaxis=None)

    def vector_subplot_hv(self, legend_name=None,colorscheme=None,field_to_apply=None, column_number=3, subplot_size=400):
        """
        Plot the vector time series with holoviews, one plot per date.

        Either give the name of a product legend, or a custom colour scheme with the
        field it applies to.

        Args:
            legend_name (str, optional): name of the product legend.
            colorscheme (dict or list, optional): custom colour scheme (see
                ``Legend.detect_colorscheme_type`` for the accepted formats).
            field_to_apply (str, optional): attribute coloured by ``colorscheme``.
            column_number (int): number of columns of the layout.
            subplot_size (int): width and height of each plot, in pixels.

        Returns:
            holoviews.Layout: the plots.

        Raises:
            ValueError: if no vector data were loaded, or if neither ``legend_name``
                nor ``colorscheme`` and ``field_to_apply`` are given.
        """
        if self.data_vector is None:
            raise ValueError("No vector data were retrieved with the query provided")

        # -------------------------
        # CASE 1 : predefined legend
        # -------------------------
        if legend_name:

            colorSchemePlt = self.default_legend.get_colorscheme_for_plt(name=legend_name)
            ltype = self.default_legend.get_type(legend_name)
            field = self.default_legend.get_colorscheme_field(legend_name)[0]

        # -------------------------
        # CASE 2 : custom colorscheme
        # -------------------------
        elif colorscheme and field_to_apply:

            colorSchemePlt = colorscheme
            field = field_to_apply
            ltype = Legend.detect_colorscheme_type(colorscheme)

        else:
            raise ValueError(
                "Provide either legend_name OR (colorscheme + field_to_apply)"
            )
        time_values = sorted(set(self.data_vector['time']))

        plots = []
        for val in time_values:
            subset = self.data_vector[self.data_vector['time'] == val]
            p = self._hvplot_vector_subset(subset, field, ltype, colorSchemePlt, width=subplot_size, height=subplot_size)
            p = p.opts(title=val.strftime('%Y-%m-%d'))
            plots.append(p)

        layout = hv.Layout(plots).cols(column_number)
        return layout

    def raster_subplot_hv(self, name_dataset, colorscheme='viridis', cut_to_vector_extent=False,
                       column_number=3, subplot_size=400):
        """
        Plot the raster time series with holoviews, one plot per date.

        Args:
            name_dataset (str): name of the raster measurement to plot.
            colorscheme (str or LinearSegmentedColormap): colormap.
            cut_to_vector_extent (bool): clip the raster to the extent of the vector data.
            column_number (int): number of columns of the layout.
            subplot_size (int): width and height of each plot, in pixels.

        Returns:
            holoviews.Layout: the plots.

        Raises:
            ValueError: if no raster data were loaded.
        """
        if self.data_raster is None:
            raise ValueError("No raster data were retrieved with the query provided")

        data_raster_temp = self.get_raster_clip_to_vectors_bounds if cut_to_vector_extent else self.data_raster
        colorscheme = self._validate_colorscheme(colorscheme)
        data_masked = data_raster_temp[name_dataset].where(data_raster_temp[name_dataset] != self.nodata_value)

        plots = []
        for val in data_raster_temp.time.values:
            p = self._hvplot_raster_subset(data_masked, val, colorscheme, width=subplot_size, height=subplot_size)
            p = p.opts(title=pd.to_datetime(str(val)).strftime('%Y-%m-%d'))
            plots.append(p)

        layout = hv.Layout(plots).cols(column_number)
        return layout

    def raster_vector_subplot_hv(self, legend_name, name_dataset, colorscheme='viridis',
                               cut_to_vector_extent=False, extrapolation=None,
                               time_range='D', column_number=3, subplot_size=400):
        """
        Plot each raster date with the matching vector data overlaid (holoviews).

        Same parameters and date matching as ``raster_vector_subplot``, plus
        ``subplot_size`` (width and height of each plot, in pixels).

        Returns:
            holoviews.Layout: the plots.
        """
        if (self.data_raster is None) or (self.data_vector is None):
            missing = []
            if self.data_raster is None: missing.append("raster")
            if self.data_vector is None: missing.append("vector")
            raise ValueError(f"No {' and '.join(missing)} data were retrieved with the query provided")

        time_val_raster = self.data_raster.indexes['time'].values
        time_val_vect = np.unique(self.data_vector['time'])
        datasets = self.dc.find_datasets(product=self.productVector, **{'time': self.query_for_vect.get('time')})
        ds, *_ = datasets
        extrapolation_value = extrapolation if extrapolation is not None else ds.product.lookup_attributes().get(
            list(ds.product.lookup_attributes().keys())[0]).get('extrapolation', False)
        dates_to_run = self._create_time_extrapolation(time_val_raster, time_val_vect, time_range, extrapolation_value)

        data_raster_temp = self.get_raster_clip_to_vectors_bounds if cut_to_vector_extent else self.data_raster
        data_vect_temp = self.data_vector if self.rast_crs == self.vect_crs else self.data_vector.to_crs(self.rast_crs)
        colorSchemePlt = self.default_legend.get_colorscheme_for_plt(name=legend_name)
        ltype = self.default_legend.get_type(legend_name)
        field = self.default_legend.get_colorscheme_field(legend_name)[0]
        data_masked = data_raster_temp[name_dataset].where(data_raster_temp[name_dataset] != self.nodata_value)

        if np.isnan(data_masked).all():
            raise ValueError("raster only composed of no data values")

        plots = []
        for i, val in enumerate(dates_to_run['raster']):
            # Base raster
            p = self._hvplot_raster_subset(data_masked, val, colorscheme, width=subplot_size, height=subplot_size)

            # Vector overlay if a matching date is available
            vector_val = dates_to_run.iloc[i]["vector"]
            if vector_val is not pd.NaT and not pd.isnull(vector_val):
                subset = data_vect_temp[data_vect_temp['time'] == vector_val]
                v = self._hvplot_vector_subset(subset, field, ltype, colorSchemePlt, width=subplot_size, height=subplot_size)
                p = p * v
                title = (f"raster: {pd.to_datetime(str(val)).strftime('%Y-%m-%d')}\n"
                         f"vector: {pd.to_datetime(str(vector_val)).strftime('%Y-%m-%d')}")
            else:
                title = (f"raster: {pd.to_datetime(str(val)).strftime('%Y-%m-%d')}\n"
                         f"vector: None")

            p = p.opts(title=title)
            plots.append(p)

        layout = hv.Layout(plots).cols(column_number)
        return layout

def create_linear_cmap(
    values: Optional[List[Union[float,int]]] = None,
    colors: Optional[List[str]] = None,
    dict_values_colors: Optional[List[Union[Dict, List]]] = None,
    name: str = 'custom'
) -> LinearSegmentedColormap:
    """
    Create a linear matplotlib colormap from values and colours.

    The values are normalised between their minimum and maximum, so that each
    colour is placed at the position of its value.

    Args:
        values (list of number, optional): values.
        colors (list of str, optional): colours corresponding to the values.
        dict_values_colors (list, optional): alternative to ``values`` and
            ``colors``: list of dicts ``{'value': v, 'color': c}`` or of lists
            ``[v, c]``.
        name (str): name of the colormap.

    Returns:
        LinearSegmentedColormap: the colormap.

    Raises:
        ValueError: if the parameters are invalid.
    """
    
    if dict_values_colors:
        if (all(isinstance(n, dict) for n in dict_values_colors)) and (all({'value','color'}.issubset(item.keys()) for item in dict_values_colors)):
            values = [d['value'] for d in dict_values_colors]
            colors = [d['color'] for d in dict_values_colors]
        elif all(isinstance(n, list) for n in dict_values_colors):
            values = [item[0] for item in dict_values_colors]
            colors = [item[1] for item in dict_values_colors]
        else:
            raise ValueError("invalid dict_values_colors")

    if not (values and colors and len(values) == len(colors)):
        raise ValueError("invalid values and colors")

    min_val, max_val = min(values), max(values)
    normalized_points = [((v - min_val) / (max_val - min_val), c) for v, c in zip(values, colors)]
    
    return LinearSegmentedColormap.from_list(name, normalized_points)
