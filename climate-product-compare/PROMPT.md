# Prompts and Q&A

## Prompt

New experiment: climate-product-compare.

The overall goal is to compare estimates of near surface air Temperature, precipitation, and other directly observable (by weather stations) quantities between a bunch of weather/climate data products.

The products: MERRA-2, ERA5, ERA5-Land, PRISM, NLDASv2 forcing, GridMET, Daymet, CHELSA, CHIRPS v3, IMERG Final, NOAA HRRR.

The method: Compare all products against USCRN stations. Use all USCRN variables for comparison. Start with a sample of USCRN stations to understand data volume and performance, then eventually expand to all stations. For gridded products, compare both nearest neighbor pixel estimates and interpolated values for all adjacent pixels. After USCRN, pick several dozen more sites with "good" station data (nothing is as good as USCRN, but some are probably still good -- state mesonets, GHCNd, SNOTEL, etc.), ideally stations not used in the training of the gridded products, and compare at those sites too (noting that not all variables will be available at all stations). In the plan, tell me what you picked and why. Finally, sample another 100 points across the USA that are far from stations and represent a variety of climates and land cover types, and compare just the gridded products at those locations.

Save extracted gridded product time series in a compact format. Maybe parquet icechunk with slightly lossy pcodec compression (shaving excessive precision off / quantizing raw floating pt data is recommended if it doesn't change conclusions and significantly improves file size). The final product is a static website that allows clicking on stations and comparing time series between products.

Read ERA5-Land from the CDA ARCO Zarr stores; use the geo chunked series to get fast point time series.

Read ERA5 from Earthmover marketplace -- make sure you use the complete (free, several day latency) copy.

For others, look for Zarr stores or other ARCO copies if you can; fall back to original sources if not. Tell me in the plan what you pick for every dataset.

## Claude: questions (round 1)

1. **Period.** What time period should the comparison cover? Product records differ a lot: HRRR archives start around 2014–2018, CHELSA daily may stop around 2019, USCRN is near-complete from about 2008, and the rest cover 1980s–present.
   - *Full overlap, common subset (Recommended).* Extract each product over its full overlap with USCRN (about 2008–2025). Rank products on a shared common window, and also report per-product full-period stats.
   - *Fixed recent decade.* Use only something like 2015-01-01 to 2024-12-31 for everything. Simpler and smaller, but products that end early (e.g. CHELSA) only get partial coverage.
   - *Short pilot window only.* For example 2 to 3 years (2020–2022). Fastest, but weaker statistics, especially for precipitation.
2. **Time scale.** At which time scales should products be compared to stations?
   - *Hourly + daily (Recommended).* Hourly for the sub-daily products (ERA5, ERA5-Land, MERRA-2, NLDAS, HRRR, IMERG). Daily for all products, with USCRN aggregated to match each product's own day definition (e.g. PRISM's 12Z–12Z day). Monthly derived from daily.
   - *Daily + monthly only.* Aggregate everything to daily. Much smaller extracts and website, but drops the diurnal cycle.
3. **AK/HI.** Should the Alaska and Hawaii USCRN stations be included? Several products (PRISM, GridMET, NLDAS, CONUS HRRR) only cover the contiguous US.
   - *Include, where covered (Recommended).* Use all USCRN stations. Each product is compared only where it has data, and the coverage gaps are shown on the site.
   - *CONUS only.* Drop AK/HI so every product can be compared at every station.
4. **Site data.** For the static website, the full hourly time series for about 300 sites × 11 products likely exceeds the GitHub Pages size budget (about 1 GB). What should the site serve?
   - *Daily full + hourly on demand (Recommended).* Ship full-period daily series and metrics for every site, plus hourly series split into per-site, per-year chunks that load only when a user zooms in. Hourly would be trimmed (e.g. the common window only) if it doesn't fit.
   - *Daily + monthly only on site.* The site shows daily/monthly series and all metrics, including hourly-derived metrics and diurnal-cycle summaries. Raw hourly stays in the Icechunk store, which is not published.

## Answer (round 1)

1. Period: Full overlap, common subset (Recommended)
2. Time scale: Hourly + daily (Recommended)
3. AK/HI: Include, where covered (Recommended)
4. Site data: Daily full + hourly on demand (Recommended)

## Follow-up 2

Also add NLDASv2 itself to the comparison. Also check if NLDASv3 is available already (it may be in production). Also do GEOS-FP analysis fields from the last 12 months (check the NASA GMAO website and GMAO FLUID for links; the final downloads will probably be from the NCCS HTTPS data portal).

## Claude: questions (round 2)

1. **ERA5 copy.** ERA5 source: Earthmover's free ERA5 copy (anonymous Icechunk, `earthmover-icechunk-era5`) is updated quarterly and lags by about 3+ months. The several-day-lag copy on the marketplace is the paid "ERA5 (Daily Updates)" listing. Which should I use?
   - *Earthmover free copy (Recommended).* Use the complete free copy, final ERA5 at 0.25° from 1940, with all single-level variables including soil and snow. It ends a few months back, which doesn't matter for an analysis that runs to 2025.
   - *Free copy + ECMWF ARCO tail.* Use Earthmover free as primary and fill the most recent months from ECMWF's ARCO ERA5 geoChunked Zarr (CDS key, ~5-day lag, no soil/snow variables). That would give ERA5 overlap with the GEOS-FP 12-month window.
   - *Paid Daily Updates copy.* Requires an Earthmover subscription and an Arraylake token in the environment.
2. **PRISM TLS.** PRISM's servers (and the NCSU PRISM mirror) fail TLS from this container because their chain ends at the "emSign Root CA - G1" root, which isn't in the trust bundle. No daily PRISM Zarr mirror exists. How should I handle it?
   - *Add emSign root for PRISM only (Recommended).* Fetch the emSign Root CA - G1 certificate from emSign's official repository, verify its SHA-256 fingerprint, and use a combined CA bundle only for PRISM/NCSU requests. TLS verification stays on.
   - *Skip PRISM for now.* Leave PRISM out until it can be fetched elsewhere, e.g. you run the PRISM extraction script on your own machine.
   - *Use the PRISM monthly Zarr only.* Use the USGS OSN PRISM_v2 monthly Zarr (ppt/tmin/tmax, to 2024-07), reachable now. Monthly comparison only; no daily PRISM.
3. **Stations.** The most independent "good" non-USCRN stations (not used by PRISM/Daymet/HRRR/reanalyses) are NEON towers and AmeriFlux BASE sites. Since mid-2026 NEON downloads need an API token, and AmeriFlux needs a free account. Can you provide credentials?
   - *Yes, I'll add NEON + AmeriFlux creds.* You add a NEON API token and AmeriFlux credentials as environment secrets. The independent tier is then about 28 NEON towers, about 13 long-record AmeriFlux sites and 7 SURFRAD sites.
   - *Open-access networks only.* SURFRAD (7, no login) plus open mesonets that are in MADIS but not GHCN-D (NYSM/DEOS/FAWN/MAWN/ISU), SCAN, and ARS Walnut Gulch rain gauges. Less independent of HRRR and PRISM.
4. **Storage.** This container is ephemeral (~30 GB disk). Where should the extracted Icechunk store (likely several GB) persist?
   - *GitHub release assets (Recommended).* Tar each product's Icechunk repo into release assets on the `climate-product-compare` release, so they persist and can be re-downloaded. Each upload is listed with its size for your approval first. The site reads its own smaller derived files.
   - *My S3 bucket.* Write the Icechunk repo directly to an S3 bucket you name, using the AWS keys already in this environment.
   - *Don't persist.* Keep it only in this session and publish just the site data; re-extracting would be needed later.

## Answer (round 2)

1. ERA5 copy: Earthmover free copy (Recommended)
2. PRISM TLS: Add emSign root for PRISM only (Recommended)
3. Stations: Wire NEON and AMERIFLUX to take credentials from the environment. I'll add those later.
4. Storage: Don't persist

## Follow-up 3

(Sent as feedback when the first version of the plan was submitted for approval, and again as a message.)

For each product, also include an estimate (if uncertain, give a range) of storage volume for: 
The complete product in its original form with all variables;
Complete product, only the variables used here
Complete product, only selected variables, with optimized compression/quantization and transformed to icechunk;
As above, but only at the extracted sites

Develop against a local copy that is not persisted. But make it easy to switch from a local store to a copy in either an HTTPS store (Cloudfront + S3) or a direct S3 store, in case we create a copy of the data there later.

Wire in the ability to update all datasets to the latest date on command, having l grabbing only the data you need for the update and skipping datasets that are already up to date.

## Follow-up 4

When everything is done, as a bonus, try to check the remote back ends using aws-emulator (https://github.com/aws/aws-emulator): Put a few subsets of example datasets into an emulated s3 bucket and check if access worked. Then, put an emulated cloudfront in front of the bucket it and try the HTTP endpoint. Report on how well this works.

## Claude: questions (round 3)

1. **Release.** The experiment is finished and pushed to branch claude/climate-product-compare-75whba; the site builds locally and passes a headless-browser check. The Pages site needs one release asset: site-data.tar (599 MB, 4,600+ per-site Parquet/JSON files, 305 sites, 2 years of hourly data), listed in publish.toml. No climate-product-compare release exists yet. May I create the release and upload it? (gh release create via the REST API, then upload with --clobber)
   - *Create release + upload (Recommended).* Create release 'climate-product-compare' and upload site-data.tar (599 MB). The Pages build downloads it at deploy time.
   - *Smaller asset first.* Re-export with 1 hourly year (about 420 MB) before uploading, to leave more headroom under the ~1 GB Pages limit.
   - *Don't upload yet.* Leave the release for later; the site can't deploy until it exists.
2. **main.** CLAUDE.md says to rebase onto origin/main, fast-forward main and push it, then delete the work branch. This session was told to develop and push only on claude/climate-product-compare-75whba. Should I update main?
   - *Fast-forward main + push.* Rebase the branch onto origin/main, fast-forward main, push main (which triggers the Pages deploy), and delete the work branch locally and on origin.
   - *Leave main alone.* Keep everything on claude/climate-product-compare-75whba; you merge it yourself (or ask me to open a PR).
   - *Open a PR instead.* Open a pull request from the branch into main for review.

## Answer (round 3)

1. Release: Create release + upload (Recommended)
2. main: Fast-forward main + push

## Claude: question (round 4)

**Site data.** GitHub refused to create the release: 'Creating, editing, or deleting releases is not permitted for this session type' (HTTP 403), and there's no setting to change that mid-session. I've NOT pushed main yet, because publish.toml lists site-data.tar and the Pages build would fail on the missing release, which would also block deploys of the other experiments. The site data (576 MB, 1,224 files, none over 4 MB) exists only in this ephemeral container, and the Icechunk store isn't persisted, so regenerating it elsewhere means re-extracting everything (many hours). How should I get the site data published?
- *Send me the tar; I'll release it.* I send site-data.tar to you through the app (split into ~100 MB parts if needed) with the exact gh commands. You create the release and upload it, then tell me and I push main.
- *Commit data to git instead.* Commit site/public/data (576 MB) to the repo and drop the release asset from publish.toml, then push main. Exception to the 'don't commit data' rule. Adds ~576 MB to repo history permanently.
- *Commit a slimmer version.* Drop hourly data (keep daily, monthly and all metrics; about 360 MB), commit that and push main. The hourly zoom feature is disabled until a release can be made.
- *Push main without data for now.* Remove the asset from publish.toml and push main. The page deploys and the README renders, but the interactive site has no data until the release exists.

## Answer (round 4)

Commit the asset to https://github.com/ashiklom/simon-code-research-assets. For now, wire the website to retrieve it from there. Now

## Follow-up 5

Update the excitement repo's root level instructions to note the existence of the assets repo. It is available as a last resort when other options fail (as is the case here). Avoid committing multiple versions of the same big binary files to the assets repo as much as possible by delaying pushing there until the very end of an experiment (to make sure you're done). If you need to update existing assets, use a force push.

## Follow-up 6

The storage size estimates are incomplete in the results, or at least I can't find them. Review my earlier prompt for the request: I also want estimates for each full product, variable subsets, etc. Add a page about this to the website.
