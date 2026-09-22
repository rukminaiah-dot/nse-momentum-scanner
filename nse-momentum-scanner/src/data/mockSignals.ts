import { Signal } from '../types/signal';
export const mockSignals: Signal[] = [
 {symbol:'DEMO1',name:'Paper Signal A',price:1248.5,changePct:0.74,relativeVolume:2.6,score:86,trend:'Bullish',reason:'Above VWAP + rising relative volume + bullish reversal confirmation',invalidation:'Below VWAP / reversal low',observedAt:'Paper mode'},
 {symbol:'DEMO2',name:'Paper Signal B',price:782.2,changePct:0.51,relativeVolume:1.9,score:78,trend:'Bullish',reason:'EMA alignment + volume expansion + sector strength',invalidation:'Break below setup low',observedAt:'Paper mode'}
];
