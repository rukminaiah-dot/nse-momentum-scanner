"""User-provided watchlist from image dated 8 Oct 2026.
The source image contains 57 rows, including KAYNES twice: 56 unique tickers.
Image prices and analyst targets are NOT verified market feeds.
"""
LARGE = ["BEL","LT","SBIN","BHARTIARTL","NTPC","M&M","SUNPHARMA","HDFCBANK","TATASTEEL","TITAN","CIPLA","INFY","GODREJPROP","ONGC","JSWSTEEL","EICHERMOT","TATACONSUM","TCS"]
MID = ["DIXON","POLYCAB","CUMMINSIND","PERSISTENT","INDHOTEL","ASTRAL","SOLARINDS","AUBANK","MAXHEALTH","CONCOR","KFINTECH","APLAPOLLO","SUZLON","KAYNES","BSOFT","CDSL","APOLLOTYRE","CYIENT","SANGHVIMOV","NCC"]
SMALL = ["VEDL","SJVN","BAJFINANCE","INFODEGE","GODREJAGRO","ONMOBILE","DHANLAXMI","AEGISLOG","AMBER","MAZDOCK","BDL","CHAMBLFERT","CESC","RBLBANK","POLYCAB","KFINTECH","APTUS","SANSERA","KAYNES"]
# Some small-cap tickers in the image may be miscategorized; category is image-provided only.
# Duplicates span sections (POLYCAB, KFINTECH, KAYNES). Validate NSE symbols before market lookup.
WATCHLIST = list(dict.fromkeys(LARGE + MID + SMALL))
