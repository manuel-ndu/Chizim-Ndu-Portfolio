# Chizim Ndu | Portfolio

Personal portfolio site for Chizim Ndu, data and business analyst in Toronto.

## TTC subway delay analysis

`analysis/ttc_delays.py` downloads the City of Toronto's open TTC subway delay data,
cleans it with pandas and writes `data/ttc_summary.json`. The website charts that file.

A GitHub Actions workflow (`.github/workflows/build.yml`) reruns the analysis every
Monday and the site redeploys on Vercel, so the charts stay current with no manual work.

Data: [City of Toronto Open Data, TTC Subway Delay Data](https://open.toronto.ca/dataset/ttc-subway-delay-data/)
(Open Government Licence – Toronto).

Built with Python, pandas, Chart.js, GitHub Actions and Vercel.
