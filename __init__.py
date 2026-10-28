# This file is part of dcVector.
#
# Copyright (c) 2025-2026 Sébastien Chognard
# Copyright (c) 2025-2026 University of Geneva
# SPDX-License-Identifier: Apache-2.0
"""
Package to load and manipulate vectors data within the datacube env
Main modules:
- forJupyter: tools to visualise vectors data with proper legend and map viewer
- vectors: tools to load vectors data and manipulate both vectors/rasters data
"""

from .forJupyter import Legend, TemporalMapViewer
from .vectors import create_shape_geometry, Load, create_linear_cmap

__version__ = "1.0.0"
__author__ = "Chognard Sebastien sebastien.chognard[at]unige.ch"
__all__ = ["Legend", "TemporalMapViewer", "create_shape_geometry", "Load","create_linear_cmap"]