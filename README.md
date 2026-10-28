# dcVector

A plugin for handling vector data within the Cube-in-a-Box (CiaB) framework.

## Overview

dcVector extends the Open Data Cube (ODC) so that it can manage vector data natively, alongside raster data, in CiaB environments.

## Repository contents

| Path | Content |
|---|---|
| `vectUpdate.sh` | Installation script |
| `LICENSE`, `NOTICE` | Apache License 2.0 and attribution notices |
| `__init__.py`, `vectors.py`, `forJupyter.py` | New `datacube.vectors` module (loading, analysis and visualisation of vector data) |
| `core.py`, `query.py`, `__init__model.py`, `dataset.py`, `metadata.py`, `product.py`, `_products_abstract.py`, `_products_postgres.py`, `_metadata_types.py` | Modified versions of datacube-core files (see [Credits and license](#credits-and-license)) |
| `dataset-type-schema-vect.yaml`, `metadata-type-schema-vectors.yaml` | Schemas for vector products and metadata types |
| `vectData.odc-metadatatype.yaml` | Vector metadata type, to add to the index after installation |
| `testYaml/bd_ocsol/` | Product and dataset definitions for the test data |
| `testJupyter/test_install_vectors.ipynb` | Notebook to test the installation with the test data |
| `testData/ocs2003/` … `testData/ocs2021/` | Test data: land-cover shapefiles for 2003, 2012, 2015, 2018 and 2021, under ODbL v1.0. Available in the GitHub repository only, not in the release archives (see [Test data](#test-data)) |

## Installation

### Prerequisites
- Existing CiaB installation from [LivingEarthLab/cube-in-a-box](https://github.com/LivingEarthLab/cube-in-a-box), version **v1.0.0** (ships datacube 1.9.14)
- Python environment with appropriate permissions
- Access to the docker containers
- A datacube version matching the patched files (see [Version check](#version-check))

### Installation Steps

**IMPORTANT**: Before proceeding with the installation, ensure you have backed up your existing CiaB installation.

To install the vector handling components, copy the whole content of this repository (including the `testData/`, `testYaml/` and `testJupyter/` folders; see [Test data](#test-data) to get `testData/`) into the `cube_in_a_box/jupyter-user` docker container, at the following location: `/home/test/`. A different location can be chosen, but the paths in the test dataset YAML files (`/home/test/testData/...`) would then have to be edited accordingly. Then run the installation script:

```bash
/home/test/vectUpdate.sh
```

The script moves to its own directory before running, so it can be launched from anywhere.

### Choosing the target environment

By default, the script locates the datacube package automatically with the `python` found in the current environment:

```bash
python -c "import datacube, os; print(os.path.dirname(datacube.__file__))"
```

The following options are available:

| Option | Example | Effect |
|---|---|---|
| `PYTHON=` | `PYTHON=/opt/conda/bin/python ./vectUpdate.sh` | Interpreter used to detect datacube and to install the dependencies (`$PYTHON -m pip`) |
| `$1` (optional) | `./vectUpdate.sh /path/to/datacube` | Forces the path of the datacube package |
| `EXPECTED=` | `EXPECTED=1.9 ./vectUpdate.sh` | Expected datacube version (prefix accepted, default `1.9.14`) |
| `FORCE=1` | `FORCE=1 ./vectUpdate.sh` | Proceeds even if the datacube version does not match |

When a path is forced with `$1`, the script warns if it differs from the datacube seen by `$PYTHON`, because the dependencies would then be installed in another environment than the patched files.

At startup, the script prints the interpreter, the datacube version and the detected path.

### Version check

The replaced files are tied to a specific ODC version: they were written for **datacube 1.9.14**, as shipped with **Cube-in-a-Box v1.0.0** from [LivingEarthLab/cube-in-a-box](https://github.com/LivingEarthLab/cube-in-a-box). You can check the installed version with:

```bash
python -c "import datacube; print(datacube.__version__)"
```

The script stops if the installed datacube version does not match `EXPECTED`. Use `EXPECTED=<version>` to target another version, or `FORCE=1` to bypass the check at your own risk.

### What the Installation Does

The `vectUpdate.sh` script performs the following operations:

1. **Checks**: Verifies the datacube path, the datacube version and the presence of all plugin files before changing anything
2. **Backup Creation**: Creates backup copies of the replaced files by appending `.orig`, to preserve your current setup (existing backups are kept)
3. **Package install**: Installs the required Python packages (leafmap, rasterstats, hvplot, geoviews, joblib) with `$PYTHON -m pip`
4. **Directory Structure**: Creates a new `vectors/` folder inside the datacube package for vector-specific modules
5. **File Deployment**: Copies the new and patched files into the datacube package:
   - `api/core.py`, `api/query.py`
   - `model/__init__.py`, `model/schema/dataset-type-schema-vect.yaml`, `model/schema/metadata-type-schema-vectors.yaml`
   - `scripts/dataset.py`, `scripts/metadata.py`, `scripts/product.py`
   - `index/abstract/_products.py`, `index/postgres/_products.py`, `index/postgres/_metadata_types.py`
   - `vectors/__init__.py`, `vectors/forJupyter.py`, `vectors/vectors.py`

### Installation Requirements

- Ensure write permissions to the datacube package directory
- Verify that the DataCube environment is not actively running during installation

### Reinstalling after a restart

dcVector is an ad hoc plugin: it patches the datacube package installed **inside** the user's `jupyter-user` container. This container is rebuilt from scratch each time the CiaB docker stack is restarted, so everything it contains is lost: the plugin files copied into `/home/test/`, the patched datacube files, the `vectors/` folder and the Python packages installed by the script.

**After each restart, repeat the full installation:**

1. Copy the content of this repository again into `/home/test/` inside the new `jupyter-user` container
2. Run the installation script:

```bash
/home/test/vectUpdate.sh
```

The products, datasets and metadata type already added to the index are stored in the database, which runs in its own docker container and is kept between restarts. They do not need to be added again.

## Post-Installation

After successful installation, the vector handling capabilities will be integrated into your DataCube environment.

### Metadata Configuration

Before using DataCube with vector capabilities, you must add the vector metadata type (`vectData.odc-metadatatype.yaml`, provided with the plugin):

```bash
datacube metadata add --vect /home/test/vectData.odc-metadatatype.yaml
```

### Installation Verification

To verify your installation and explore the vector functionality, the test data (`testData/`) and their product and dataset definitions (`testYaml/bd_ocsol/`) are provided:

```bash
# Add the ocs vector product
datacube product add --vect /home/test/testYaml/bd_ocsol/occupationDuSol_ocs.yaml

# Add the ocs datasets
datacube dataset add -p ocs /home/test/testYaml/bd_ocsol/ocs_20*.yaml
```

### Example Usage

To explore the vector handling capabilities through practical examples, run the provided Jupyter notebook. Open the following URL in your browser, replacing `<userName>` with your JupyterHub user name, and execute the `testJupyter/test_install_vectors.ipynb` notebook:

```url
http://localhost/jupyter/user/<userName>/lab
```

This notebook demonstrates the integration of vector data processing within the DataCube environment.

### Documentation

Refer to the individual script documentation for detailed usage instructions and API references.

## Uninstall / Restore

The original datacube files are kept next to the patched ones with a `.orig` suffix. To restore them:

```bash
pathDc=$(python -c "import datacube, os; print(os.path.dirname(datacube.__file__))")

# Restore the original files
for f in api/core.py api/query.py model/__init__.py \
         scripts/dataset.py scripts/metadata.py scripts/product.py \
         index/abstract/_products.py index/postgres/_products.py \
         index/postgres/_metadata_types.py; do
  [ -f "$pathDc/$f.orig" ] && mv "$pathDc/$f.orig" "$pathDc/$f"
done

# Remove the files added by the plugin
rm -rf "$pathDc/vectors"
rm -f "$pathDc/model/schema/dataset-type-schema-vect.yaml" \
      "$pathDc/model/schema/metadata-type-schema-vectors.yaml"
```

Vector products, datasets and the vector metadata type already added to the index are not removed by this procedure. The Python packages installed by the script (leafmap, rasterstats, hvplot, geoviews, joblib) are also kept.

## Test data

The test data in `testData/` are a subset of the land-cover (occupation du sol) dataset produced by Le Grand Narbonne Communauté d'Agglomération, covering the area of the Grand Narbonne and the Parc naturel régional de la Narbonnaise en Méditerranée (Aude, Occitanie, France), for the years 2003, 2012, 2015, 2018 and 2021. They are provided in ESRI Shapefile format, in Lambert-93 (EPSG:2154).

**Source:** Le Grand Narbonne Communauté d'Agglomération, *Occupation du sol : 2003, 2012, 2015, 2018, 2021 et 2024 sur le territoire du Grand Narbonne Communauté d'Agglomération et du Parc naturel régional de la Narbonnaise en Méditerranée*. The files used here are the homogenised versions (`*_hom`) of the 2003, 2012, 2015, 2018 and 2021 editions. The dataset is available from:

- [OpenIG](https://ckan.openig.org/dataset/occupation-du-sol-sur-le-territoire-du-grand-narbonne-communaute-dagglomeration)
- [data.gouv.fr](https://www.data.gouv.fr/datasets/occupation-du-sol-2003-2012-2015-2018-2021-et-2024-sur-le-territoire-du-grand-narbonne-communaute-dagglomeration-et-du-parc-naturel-regional-de-la-narbonnaise-en-mediterranee)

**Getting the test data:** the `testData/` folder is available in the GitHub repository, but it is **not included** in the release archives (GitHub release and Zenodo). To get it, either clone the GitHub repository, or download the data from one of the links above and place the shapefiles of each year in `testData/ocs<year>/`, with the file names expected by the dataset YAML files in `testYaml/bd_ocsol/` (e.g. `testData/ocs2003/OCSOL_GN_PNR_2003_hom.shp`).

**Licence:** the data are made available under the [Open Data Commons Open Database License (ODbL) v1.0](https://opendatacommons.org/licenses/odbl/1-0/). They are **not** covered by the Apache License 2.0 of the code. Any redistribution or adaptation of these data must keep the attribution to Le Grand Narbonne Communauté d'Agglomération and remain under the ODbL (see `testData/LICENSE.md`).

**Attribution:** Contains data from Le Grand Narbonne Communauté d'Agglomération – Occupation du sol (2003, 2012, 2015, 2018, 2021), ODbL v1.0.

The data are redistributed in the GitHub repository only to test the installation of dcVector. For the full and up-to-date dataset (including the 2024 edition) and its documentation (nomenclature and minimum mapping units), refer to the original publication linked above.

## Credits and license

dcVector is developed by Sébastien Chognard ([ORCID 0009-0009-3062-4029](https://orcid.org/0009-0009-3062-4029)), University of Geneva.
Copyright (c) 2025-2026 Sébastien Chognard and University of Geneva.

- `vectors.py`, `forJupyter.py`, `__init__.py` and `vectUpdate.sh` are original work.
- `core.py`, `query.py`, `__init__model.py`, `dataset.py`, `metadata.py`, `product.py`, `_products_abstract.py`, `_products_postgres.py` and `_metadata_types.py` are modified versions of files from [datacube-core](https://github.com/opendatacube/datacube-core) 1.9.14, Copyright (c) 2015-2026 ODC Contributors, licensed under the Apache License 2.0. They were modified to add vector data support; the original copyright headers are kept and each modified file carries a modification notice (see `NOTICE`).

The code of this repository is distributed under the Apache License 2.0 (see `LICENSE` and `NOTICE`). The test data are not covered by this licence (see [Test data](#test-data)).

## Acknowledgements

All the developments have been made possible thanks to the financial support of the European Union's Horizon Europe Programme, which funded the [LandShift](https://landshift.eu/) project (Grant Agreement no. 101182007).

## Citation

<!-- Add the Zenodo DOI and the reference of the technical note once available -->
If you use dcVector, please cite the Zenodo release and the associated technical note.

## Version History

- **v1.0.0**: First public release
- **v1.0** (28/07/25): Initial internal version with core vector handling functionality

## Support

For issues or questions regarding dcVector, please open an issue on this repository.
