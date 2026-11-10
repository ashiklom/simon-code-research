# PSF / footprint sources (research notes, compiled by a research sub-agent; [derived] = our arithmetic)

Conversions: Gaussian matching MTF at Nyquist: sigma = sqrt(-2 ln MTF_N)/pi (samples); sigma = FWHM/2.355.

## MODIS 1 km TIR (bands 31/32)
- 705 km; 20.3 rpm two-sided mirror; 1354 frames over +-55 deg in 1.477 s [B98]; scan period 1.4771 s, 10 x 1354 per scan [MCST L1B UG].
- Sample spacing = IFOV = 110 deg/1354 = 1.418 mrad (1.0 km nadir) [derived]; 2.01 km track x 4.83 km scan at 55 deg (VZA 65.5) [derived].
- Along-scan LSF triangular (integration blur), along-track "more rectangular" [B98 Fig 3]; triangle base 2 samples, FWHM 1; ~75% signal from nominal pixel [Tan06, citing Nishihama et al. 1997; Barnes et al. 1998].
- Prelaunch Terra PFM [B98 Table III]: B31 scan FWHM 1120 m, track 1012.5 m, MTF_N scan 0.34 track 0.54; B32 1078 / 1012 m, 0.37 / 0.55. Spec MTF_N >= 0.3; on-orbit SRCA OK [Link17]. Ideal triangle MTF_N 0.405, rect 0.637 [Lin13].
- Bow-tie overlap ~ 1 - 1 km / d_track(theta): 7% @20, 15% @30, 27% @40, 33% @45, 41% @50, 50% @55 deg [derived]; "almost 50%" at scan end [Tan06].
- Model: scan = triangle(base 2) * Gaussian sigma 0.14-0.19; track = rect(1) * Gaussian sigma 0.17-0.18 [derived to match measured MTF_N].
- Campagnolo & Montano 2014 Gaussian fits are for 250 m gridded reflectance, not TIR swath.

## VIIRS M15/M16
- 828 +- 12 km [VGeoATBD]; 829.8 km equator, ~840 km mean [Lin13]; scan 1.7864 s, 3.5172 rad/s, +-56.063 deg, 6304 native samples per M detector, dwell 88.259 us [VGeoATBD]. 2x(640+736/2)+3552/3 = 3200 [derived].
- 16 detectors; 312 urad along-scan (1x1), 891 urad along-track [Lin13].
- Aggregation 3x1 within +-31.589 deg (native 1377-4928), 2x1 to 44.680 deg, 1x1 beyond [VGeoATBD].
- Bow-tie deletion: 1 detector each edge in 2x1 zone, 2 each edge in 1x1 zone [Lin13; W13]; overlap begins ~19 deg; scan 11.9 km wide nadir, 25.9 km at edge [VGeoATBD].
- M15/M16 pixel 0.742 x 0.776 km nadir, 1.60 x 1.58 km edge [VGeoATBD Tab 2.2-1]; native 0.742 x 0.259 km nadir.
- Response: triangular time-weighted, in practice trapezoidal [VGeoATBD]; track LSF "essentially squares", FOV within +-5% of HSI [W13].
- Measured SNPP M15/M16 [Lin13 Figs 2-5]: scan GDFOV/HSI 1.15-1.17 (1x1), ~1.00 (2x1, 3x1); MTF_N 0.35 / 0.54 / 0.59; ensquared energy 71 / 85 / 88%. Ideal 0.405 / 0.52 / 0.58 [derived].
- Model: scan rect(1) * triangle(base 2/k); Gaussian equivalents sigma 0.33 (3x1), 0.35 (2x1), 0.46 (1x1); track rect(1) (Gaussian sigma ~0.29-0.30).

## ECOSTRESS (PHyTIR)
- ISS 400 +- 25 km [EGeoATBD] / 410 +- 20 km [H24]; mirror 25.4 rpm two-sided; scan ~1.181 s, 44 scans/scene ~52 s [L1 UG]; sweep ~53 deg; swath 384-402 km; IFOV 96 urad (38.4 m @ 400 km); 256 detectors along-track, 4-column TDI; 5400 samples per scan [Cal ATBD].
- Native 37.65 m track x 68.51 m scan at nadir (scan smear) [Cal ATBD; EGeoATBD]; smear 18 m, dwell 31.6 us, spacing ~68 m [H24]. 53 deg/5400 = 171 urad [derived].
- L1B: bands warped to band 4 (nearest neighbour), line pairs averaged 256 -> 128 lines/scan, 5632 lines/scene [Rad ASD]; L1B 75.3 m track x 68.51 m scan at nadir [Cal ATBD]; ~90 x 90 m at edge [L1 UG]; scan overlap 15-30 L1B lines depending on altitude [L1 UG].
- On-orbit [H24, bridge transects, scan angle < 8 deg]: Gaussian FWHM 157 m track x 162 m across; EIFOV 148 x 167 m (~2x the pixel). Non-Gaussian: side-lobes at -140 m (amp -0.2 track / -0.1 across) and +200 m (+0.33 / +0.3).
- Model: Gaussian sigma_track ~66.7 m (0.87-0.89 samples), sigma_scan ~68.8 m (~1.0 sample).

## Bibliography
- [B98] Barnes, Pagano, Salomonson (1998) Prelaunch characteristics of MODIS on EOS-AM1. IEEE TGRS 36(4):1088-1100. https://zenodo.org/record/1261767/files/article.pdf
- [Tan06] Tan et al. (2006) The impact of gridding artifacts on the local spatial properties of MODIS data. RSE 105:98-114. https://sites.bu.edu/cliveg/files/2013/09/tanbin03.pdf
- [MCST L1B UG] MODIS L1B Product User's Guide. https://mcst.gsfc.nasa.gov/sites/default/files/file_attachments/modis_C7_L1B_Doc/M1054_PUG_REV_E_C7.pdf
- [Link17] Link, Wang, Xiong (2017) Status of MODIS spatial and spectral characterization and performance. Proc. SPIE. https://ntrs.nasa.gov/api/citations/20170003357/downloads/20170003357.pdf
- Campagnolo & Montano (2014) IEEE TGRS 52(9):5622-5632.
- Nishihama et al. (1997) MODIS Level 1A Earth Location ATBD. https://modis.gsfc.nasa.gov/data/atbd/atbd_mod28_v3.pdf
- [VGeoATBD] NASA (2014) Revised JPSS VIIRS Geolocation ATBD (423-ATBD-002). https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/Product%20Generation%20Algorithms/NASARevisedVIIRSGeolocationATBD2014.pdf
- [W13] Wolfe et al. (2013) Suomi NPP VIIRS prelaunch and on-orbit geometric calibration and characterization. JGR-Atmos 118:11508. doi:10.1002/jgrd.50873
- [Lin13] Lin, Tilton, Wolfe, Tewari, Nishihama (2013) SNPP VIIRS spectral bands co-registration and spatial response characterization. Proc. SPIE 8866, 88661G. https://ntrs.nasa.gov/api/citations/20150001286/downloads/20150001286.pdf
- [LW19] Lin & Wolfe (2019) Overview of JPSS VIIRS geometric calibration and validation. https://ntrs.nasa.gov/api/citations/20190027537/downloads/20190027537.pdf
- [H24] Holmes et al. (2024) On-orbit spatial performance characterization for thermal infrared imagers of Landsat 7, 8, and 9, ECOSTRESS and CTI. JGR-Biogeosciences 129, e2023JG007506. https://ntrs.nasa.gov/citations/20240002367
- [EGeoATBD] ECOSTRESS L1B Geolocation ATBD (JPL D-94641, 2018). https://ecostress.jpl.nasa.gov/downloads/atbd/ECOSTRESS_L1_ATBD_Geolocation_2018-03-08.pdf
- [Cal ATBD] ECOSTRESS L1 Calibration ATBD. https://lpdaac.usgs.gov/documents/222/ECO1B_Calibration_ATBD_V1.pdf
- [Rad ASD] Smyth (2018) ECOSTRESS L1B Rad PGE ASD (JPL D-96967). https://lpdaac.usgs.gov/documents/225/ECO1B_Rad_ASD_V1.pdf
- [L1 UG] Smyth & Logan (2022) ECOSTRESS L1 Product User Guide (JPL D-57151). https://lpdaac.usgs.gov/documents/1491/ECO1B_User_Guide_V2.pdf
