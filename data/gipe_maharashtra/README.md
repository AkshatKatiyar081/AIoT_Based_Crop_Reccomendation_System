# Replication Package

**Soil Nutrient Stress, Crop System Composition, and Agro-Climatic Confounding: A District-Level Analysis of Maharashtra's Agricultural Soils**

Author: Prakash Vhankade, Gokhale Institute of Politics and Economics (GIPE), Pune
Corresponding author email: prakash.vhankade@gipe.ac.in
ORCID: 0009-0005-2436-0603

---

## Overview

This package contains the district-level analytical datasets and R code required to reproduce all tables, figures, and reported statistics in the manuscript submitted to *Agricultural Systems*. The analysis covers 34 Maharashtra districts across two Soil Health Card (SHC) programme cycles (2023-24 and 2024-25) linked to district-level fertiliser use behaviour and farmer characteristics from the 2016 Input Survey.

## Data availability statement

Raw Soil Health Card microdata (551,955 village-level records) are publicly available from the Government of India SHC portal at **soilhealth.dac.gov.in** and are not redistributed in this package due to file size and because they remain a public government dataset. The 2016 Input Survey crop, non-crop, and composite schedules are publicly available from the Ministry of Statistics and Programme Implementation (MoSPI), National Sample Survey Organisation. India Meteorological Department (IMD) daily district-level rainfall data (2009-2022) are available from the IMD, Pune.

This package begins from the **district-aggregated analytical datasets** constructed from these public sources, which are the direct inputs to every regression, table, and figure reported in the manuscript.

## Folder structure

```
replication_package/
├── README.md                          (this file)
├── data/
│   ├── snsi_final.csv                 (SNSI by district and cycle, n=68)
│   ├── master_v3_rainfall.csv         (full predictor panel, n=34)
│   ├── pc_scores.csv                  (PCA component scores, n=34)
│   └── cluster_profiles.csv           (k-means cluster summary, n=2)
├── results/
│   └── coef_table.csv                 (reported OLS and QR coefficients, for verification)
└── code/
    └── analysis.R                     (full reproducible R script)
```

## Data file descriptions

**`data/snsi_final.csv`** (68 rows = 34 districts x 2 cycles)
Soil Nutrient Stress Index (SNSI) and its five component deficiency proportions (def_N, def_P, def_K, def_OC, def_Zn) by district and SHC programme cycle. Source for Table 1, the PCA validation (Section 4.2), and Figures 1 and 2.

**`data/master_v3_rainfall.csv`** (34 rows, 37 columns)
The primary analytical dataset. Contains the 2023-24 SNSI, all five-component deficiency proportions, 2016 Input Survey predictors (fertiliser intensity, N_dominance, soil testing adoption rate, irrigation share, educational attainment, mean farmer age), crop system composition variables (pulse, oilseed, cereal, sugarcane shares), the SNSI change between cycles, and mean annual district rainfall (2009-2022, IMD). This file is the direct input for Tables 3, 4, and 5, the sensitivity analysis, the rainfall-controlled regression, and the partial correlation analysis reported in Section 4.5.

**`data/pc_scores.csv`** (34 rows)
District-level scores for the first three principal components (PC1, PC2, PC3) extracted from the five SNSI deficiency components. Used to verify Table 2 and the PC1-SNSI validation correlation (r = -0.872) reported in Section 4.2.

**`data/cluster_profiles.csv`** (2 rows)
Summary statistics (mean SNSI, mean N_dominance, mean soil testing rate, mean pulse share, mean farmer age, mean graduate share, mean organic carbon deficiency, and constituent district list) for the two k-means clusters identified in Section 4.3: the Agrarian Stress Belt (n=27) and the Coastal Buffer Zone (n=4).

**`results/coef_table.csv`**
Final reported regression coefficients for the OLS specification and the four quantile regression specifications (Q25, Q50, Q75, Q90), provided for direct verification against the numbers in Table 5 without requiring the user to re-run the full regression pipeline.

## Code

**`code/analysis.R`** reproduces, in order:

- Table 1 (SNSI stress category distribution)
- Table 2 (PCA component loadings) and the SNSI sensitivity analysis (equal, PCA, and entropy weighting; Spearman rank correlations; component correlation matrix)
- Table 3 (N_dominance correlates regression)
- Table 4 (SNSI regression, base and rainfall-controlled specifications) and the partial correlation analysis (Section 4.5)
- Table 5 (quantile regression with bootstrap standard errors and pseudo R-squared)
- The age, education, and soil testing bivariate analyses reported in Sections 4.7 and 5.3

### Not reproduced in this script

Two components of the manuscript's spatial and cartographic analysis depend on external shapefiles not included in this package:

1. **Moran's I and the spatial lag/error model tests** (Section 4.3) require a district-level spatial weights matrix built from a GADM Level 2 shapefile. The reported statistics (Moran's I = 0.284, p = 0.002) are stated directly in the script as a reference value; users wishing to reproduce the spatial test independently should obtain the Maharashtra district shapefile from GADM (gadm.org) and construct a k=4 nearest-neighbour weights matrix.

2. **Figures 1, 2, and 3** (the district choropleth maps) require the same GADM shapefile merged with `master_v3_rainfall.csv` and `snsi_final.csv`. Map generation code is available from the corresponding author on request.

3. **Supplementary Table A1** (village-level SHC testing coverage) requires raw village counts from the SHC portal and Census of India 2011 village totals, which are tabulated directly in the manuscript supplementary material rather than reconstructed here.

## Software requirements

R version 4.0 or later. Required packages: `dplyr`, `tidyr`, `quantreg`, `vars`, `sf`, `ggplot2`. Install with:

```r
install.packages(c("dplyr", "tidyr", "quantreg", "vars", "sf", "ggplot2"))
```

## Citation

If you use this replication package, please cite the manuscript:

Vhankade, P. (2026). Soil Nutrient Stress, Crop System Composition, and Agro-Climatic Confounding: A District-Level Analysis of Maharashtra's Agricultural Soils. *Agricultural Systems* (under review).

## Contact

For questions about this replication package, or to request the shapefile-dependent code for Figures 1-3 and the spatial autocorrelation tests, contact the corresponding author at prakash.vhankade@gipe.ac.in.
