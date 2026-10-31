# Sustainability records

A small Streamlit page backed by a local SQLite database. It shows the latest 30 days of electricity, water, waste and carbon records, with a few trend charts, period comparisons and CSV downloads.

## Run

```powershell
python -m pip install -r requirements.txt
streamlit run frontend.py
```

The database is created at `data/sustainability.db`. A new database is filled with clearly labelled illustrative sample records. To start empty instead:

```powershell
$env:SUSTAINABILITY_SEED_SAMPLE = "0"
streamlit run frontend.py
```

The two application files are `frontend.py` (Streamlit UI) and `backend.py` (SQLite, sample records and calculations). Use `backend.save_record({...})` to add or update an office record for a date. Measurements can be left blank.

Carbon uses reported CO2e if present. No default emissions factor is assumed. To estimate electricity emissions, configure `ELECTRICITY_EMISSION_FACTOR_KG_PER_KWH` with an authoritative factor before launching the app.
