# Weather Degree Days

Calculate Heating Degree Days (HDD) and Cooling Degree Days (CDD) from weather forecast models using the [Herbie](https://herbie.readthedocs.io/) library.

Supports fetching 2m temperature forecasts from:
- **GFS** (NOAA)
- **GEFS** (NOAA ensemble)
- **IFS** (ECMWF)
- **AIFS** (ECMWF AI model)

## Setup

```bash
pip install -r requirements.txt
```

## Usage

Open `degree_days.ipynb` in Jupyter and run the cells:

```python
extractor = DegreeDayExtractor()

gfs_ds = extractor.get_forecast(model='gfs', fxx=24)
gfs_hdd, gfs_cdd = extractor.calc_degree_days(gfs_ds)

print(f"GFS HDD: {float(gfs_hdd.mean()):.2f}")
```

Optional spatial weighting (gas consumption or population) can be applied via `DegreeDayExtractor(weights_path='weights.csv')`.
