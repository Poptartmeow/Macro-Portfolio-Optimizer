# Macro-Portfolio-Optimizer
Global Macro Portfolio Optimizer &amp; Risk Analytics Platform

## Mauricio Torres, Tianyin Mao, Jack Joy, Tiandra Threat

"""
Column naming convention:
  REAL_GDP_<COUNTRY>        Real GDP, PPP-adjusted USD (OECD, quarterly → monthly ffill)
  HEADLINE_CPI_<COUNTRY>    Headline CPI, % change year-on-year (OECD)
  IRSTCI_<COUNTRY>          Central bank policy rate, % per annum (OECD)
  IRLT_<COUNTRY>            10-year government bond yield, % per annum (OECD)
  IR3TIB_<COUNTRY>          3-month interbank rate, % per annum (OECD)
  CORE_CPI_USA              US Core CPI ex food & energy, index (FRED)
  DGS2_USA                  US 2-year Treasury yield, % (FRED)
  SPREAD_10Y3M_<COUNTRY>    10yr yield minus 3-month rate (computed)
  SPREAD_10Y2Y_USA          US 10yr minus 2yr yield (computed, US only)
  BAA10Y — Moody's Baa corporate yield minus 10yr Treasury (investment-grade spread)
  AAA10Y — Moody's Aaa minus 10yr (tighter end)
  S&P 500 dividend yield — FRED has this as a proxy (`SP500` price + `DDDM01USA156NWDB` from World Bank). US-centric but widely used as a global equity signal.
  """
