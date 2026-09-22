# NSE Momentum Scanner — V1
Personal Android-first paper-trading alert app.

## Current V1
- ₹50,000 paper capital and ₹500 daily target display
- Positive-momentum signal cards
- Relative-volume, trend, reason and invalidation fields
- Android/iOS local push-notification permission + test alert
- No live orders; demo signals are clearly marked paper mode
- `.env` excluded from Git

## Run in a cloud dev environment
```bash
npm install
npx expo start
```
Use Expo Go for early UI testing. For production push notifications / Android builds, configure an Expo/EAS project.

## Planned backend
The mobile app should call a server with a static outbound IP. The server owns Angel One SmartAPI authentication and market-data sessions. Never put Angel One secrets in the mobile bundle.

Pipeline: market feed -> liquidity universe -> VWAP/EMA/RSI/ATR/RVOL -> reversal/candlestick checks -> market/sector/news context -> score -> notification -> paper trade log.

## Safety
The scanner reports observed momentum; it does not guarantee a 1% return. V1 deliberately does not auto-execute live trades.
