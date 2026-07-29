# Midas Academy · Glossary

> A quick reference manual for trading terms, covering 10 major categories: Basic Concepts, Order Trading, Contract Derivatives, Spot & Market Mechanisms, K-Line & Charts, Technical Indicators, Chart Patterns, Chan Theory, Strategies & Arbitrage, and Risk & Mindset. Each entry includes a one-sentence definition, detailed explanation, and related terms.
---

## Table of Contents

**Basic Concepts**
1. Long / 2. Short / 3. Leverage / 4. Margin / 5. Liquidation / 6. Price Limit

**Orders & Trading**
　7. Market Order ／ 8. Limit Order ／ 9. Stop Loss ／ 10. Take Profit ／ 11. Position ／ 12. Open / Close Position ／ 13. Long Order / Short Order

**Contracts & Derivatives**
　14. Perpetual Contract ／ 15. Funding Rate ／ 16. Long/Short Ratio ／ 17. Open Interest (OI) ／ 18. Liquidation Price ／ 19. Cross / Isolated Margin ／ 20. Leverage Ratio ／ 21. Unrealized PnL ／ 80. Delivery Contract ／ 81. OI Interpretation ／ 82. Liquidation & Negative Balance

**Spot & Market Mechanisms**
　22. T+0 / T+1 (Trading Settlement Cycle) ／ 23. Circuit Breaker ／ 24. Slippage ／ 25. Liquidity ／ 26. Spot ／ 27. Market Maker ／ 28. Order Book ／ 29. Volume

**K-Line & Charts**
　30. K-Line (Candlestick) ／ 31. Bullish / Bearish Candle ／ 32. Shadow (Upper / Lower Shadow) ／ 33. Body (K-Line Body) ／ 34. Hammer ／ 35. Timeframe ／ 79. Multi-Timeframe Analysis

**Technical Indicators**
　36. MA ／ 37. Golden cross / Death cross ／ 38. MACD ／ 39. Bollinger Bands ／ 40. RSI ／ 41. Trend ／ 42. Support ／ 43. Resistance ／ 44. Consolidation ／ 45. Overbought / Oversold ／ 46. Indicator Stagnation ／ 47. Divergence ／ 48. MA Bullish Arrangement / Bearish Arrangement ／ 49. Standard Deviation ／ 50. EMA ／ 51. Bollinger Band Expansion / Contraction ／ 52. Momentum ／ 67. KDJ ／ 68. Difference between SMA and EMA ／ 69. Volume and Price-Volume Relationship ／ 70. ATR ／ 71. BIAS

**Chart Patterns**
　72. Doji ／ 73. Engulfing Pattern ／ 74. Head and Shoulders Top / Bottom ／ 75. Double Top / Double Bottom ／ 76. Gap ／ 77. Elliott Wave Theory ／ 78. Trendline and Channel Line

**Chan Theory**
　53. Chan Theory (Chan Zhong Shuo Chan Theory) ／ 54. K-Line Inclusion Relationship ／ 55. Fractal (Top Fractal / Bottom Fractal) ／ 56. Stroke ／ 57. Segment ／ 58. Central Hub ／ 59. Divergence ／ 60. Chan Theory Buy/Sell Points (Type 1, 2, 3 Buy/Sell Points)

**Strategies & Arbitrage**
　83. Grid Trading ／ 84. Martingale ／ 85. Arbitrage ／ 86. Left-side Trading / Right-side Trading

**Risk & Mindset**
　61. Paper Trading ／ 62. Risk Management ／ 63. Position Sizing ／ 64. Trade Review ／ 65. Trend Following ／ 66. Trading with the Trend ／ 87. Max Drawdown ／ 88. Overfitting

---

## Basic Concepts

### 1. Long

**One-sentence definition:** Long (establishing a long position) refers to the operational direction of "buying first and selling later" to earn price spreads, based on the expectation that prices will rise.

**Detailed explanation:** Longs believe prices will rise, so they buy at lower prices and sell after prices rise to earn the spread; if prices rise as expected, they profit; if they fall, they incur a loss. This is the most intuitive trading direction, applicable to both spot and contracts. For example, buying at 100 and selling at 120 to earn a 20 spread.

**Related terms:** Short, Leverage, Perpetual Contract

---

### 2. Short

**One-sentence definition:** Short (establishing a short position) refers to the operational direction of "selling first and buying later" to earn falling price spreads, based on the expectation that prices will fall.

**Detailed explanation:** Shorts believe prices will fall, so they sell first (borrowing and selling at high prices) and buy back at lower prices later to earn the spread; if prices fall as expected, they profit; if they rise, they incur a loss. Contracts facilitate shorting, while spot generally only allows longing. Note: Theoretically, there is no upper limit to rising prices, so the potential loss from shorting in the wrong direction can be significant.

**Related terms:** Long, Perpetual Contract, Liquidation

---

### 3. Leverage

**One-sentence definition:** Leverage refers to using a small margin to operate a position much larger than the principal.

**Detailed explanation:** For example, using 1,000 yuan margin with 10x leverage allows you to operate a position worth 10,000 yuan. Leverage **doubles the profit and loss**—small price fluctuations are magnified by multiples of the principal. ⚠️ The higher the leverage, the greater the risk, and the easier it is to be liquidated; it is a high-risk tool. Beginners should be cautious and start with low leverage. It is by no means a shortcut to "making more money," but a source of risk for "losing faster."

**Related terms:** Margin, Liquidation, Perpetual Contract

---

### 4. Margin

**One-sentence definition:** Margin is the capital deposited to hold a position when trading with leverage / contracts.

**Detailed explanation:** It is your own funds used to "leverage" a larger position. Profits and losses are calculated based on this margin—when losses approach the margin, forced liquidation (liquidation) may be triggered. The smaller the margin relative to the position (i.e., the higher the leverage), the smaller the counter-trend fluctuation you can withstand, making you more prone to forced liquidation.

**Related terms:** Leverage, Liquidation, Perpetual Contract

### 5. Liquidation

**One-sentence definition:** Liquidation (forced closing) refers to the position being forcibly closed by the system when losses approach the margin.

**Detailed explanation:** When trading with leverage / contracts, when prices move in the opposite direction and losses become large enough to approach your margin, the platform forcibly closes the position to prevent your losses from exceeding your principal. Your margin may suffer significant losses or even go to zero. ⚠️ The higher the leverage, the smaller the adverse price movement may be to trigger liquidation—this is the primary risk of high leverage.

**Related terms:** Leverage, Margin, Perpetual Contract

---

### 6. Price Limit

**One-sentence definition:** Price limit refers to the fixed amplitude ceiling set for daily price fluctuations of individual stocks in some markets.

**Detailed explanation:** When the price hits the upper limit, it is called a "Limit Up," and when it hits the lower limit, it is called a "Limit Down"; the daily price cannot exceed that amplitude. For example, the A-share main board is typically ±10%, while the ChiNext / STAR Market is ±20%. The main board ST stocks have been raised from the original ±5% to ±10% (effective from July 2026, subject to official latest rules). Cryptocurrencies generally do not have price limits; the US stock market and Hong Kong stock market generally do not have fixed daily price limits, but have circuit breakers / volatility adjustment mechanisms.

**Related terms:** Perpetual Contract (Contrast: Crypto contracts have no price limits), Circuit Breaker, T+1

---

---

## Orders and Trading

### 7. Market Order

**One-sentence definition:** A Market Order is an order to be executed immediately at the current market price.

**Detailed explanation:** Its characteristic is fast execution, almost immediate execution, but the execution price is based on the market price at that time and is not fully controllable. In volatile markets or low liquidity, "slippage" (a deviation between the actual execution price and the expected price) may occur. It is suitable for scenarios where ensuring execution is the top priority.

**Related terms:** Limit Order, Stop Loss, Take Profit

---

### 8. Limit Order

**One-sentence definition:** A Limit Order is an order placed at a specified price, waiting for the price to reach it before execution.

**Detailed explanation:** Its execution price is controllable (it will not be worse than the limit price you set), but it may not execute if the price never reaches that level. For example, if the current price is 100, placing a "Buy at 98" limit order will only execute when the price drops to 98 or lower. It is suitable for scenarios where controlling the execution price is the top priority and you are willing to wait for an ideal price.

**Related terms:** Market Order, Stop Loss, Take Profit

---

### 9. Stop Loss

**One-sentence definition:** Stop Loss refers to a pre-set exit price for losses; when the price reaches this point, you exit to control the loss on a single trade.

**Detailed explanation:** Taking Long as an example, the Stop Loss price is set **below** the entry price; when the price drops to that level, you exit, limiting the loss to a controllable range (for Short, it is set above). It is the core of trading discipline, meaning "not letting a small loss drag into a big loss." However, it is risk control and **does not guarantee profit**, and in extreme market conditions, the actual execution price may deviate from the Stop Loss price (slippage / gap).

**Related terms:** Take Profit, Market Order, Limit Order

---

### 10. Take Profit

**One-sentence definition:** Take Profit refers to a pre-set exit price for profits; when the price reaches this point, you exit to lock in profits.

**Detailed explanation:** Taking Long as an example, the Take Profit price is set **above** the entry price; when the price rises to that level, you exit, securing the floating profit (for Short, it is set below). It helps avoid the regret of "making a profit on paper but not holding it as it drops back." Like Stop Loss, it is an exit plan determined before entering the trade.

**Related terms:** Stop Loss, Limit Order, Market Order

---

### 11. Position

**One-sentence definition:** A Position refers to the current holding—how much you bought / sold and whether it is Long or Short.

**Detailed explanation:** Holding a Long position is called a Long position, and holding a Short position is called a Short position; "Flat" or "Cash" refers to having no position. The size of the position (how much capital is occupied) is directly related to risk. Controlling position size is one of the core components of risk management.

**Related terms:** Open / Close Position, Long / Short, Position Management

---

### 12. Open / Close Position

**One-sentence definition:** Opening a position means establishing a new position, and closing a position means settling an existing position.

**Detailed explanation:** After opening a position, you hold the position and bear the profit and loss; after closing a position, the position is settled, and the profit and loss are realized (taken to the bag or recognized as a loss). When Long, you buy to open and sell to close; when Short, you sell to open and buy back to close. Stop Loss and Take Profit are essentially closing actions triggered by conditions.

**Related terms:** Position, Long / Short, Stop Loss

---

### 13. Long / Short Order

**One-sentence definition:** A Long order refers to a position in the Long direction (bullish), and a Short order refers to a position in the Short direction (bearish).

**Detailed explanation:** Holding a Long order means profit if the price rises and loss if it falls; holding a Short order is the opposite. These are the names for "Positions" by direction. Contracts can have both Long and Short directions simultaneously, while Spot generally only has Long orders.

**Related terms:** Long / Long, Short / Short, Position

---

---

## Contracts and Derivatives

### 14. Perpetual Contract

**One-sentence definition:** A Perpetual Contract is a cryptocurrency derivative without an expiration date, with leverage, and allowing for two-way trading.

**Detailed explanation:** Unlike Spot, it does not hold physical assets but is a contract revolving around price changes. It allows for both Long and Short trading, comes with leverage (profits and losses are amplified, with liquidation risk), and uses a "Funding Rate" mechanism to keep the contract price close to the Spot price. ⚠️ Because it involves leverage, the risk of Perpetual Contracts is significantly higher than Spot.

**Related terms:** Funding Rate, Leverage, Liquidation / Forced Close

---

### 15. Funding Rate

**One-sentence definition:** The Funding Rate is a periodic fee paid between Longs and Shorts in a Perpetual Contract.

**Detailed explanation:** It is the mechanism that keeps the Perpetual Contract price close to the Spot price—every so often (the cycle varies by platform), fees are exchanged between Longs and Shorts. Note that this money is transferred **between Longs and Shorts**, not paid to the platform as a fee. The sign and magnitude of the rate are often used to observe market sentiment (e.g., when Long sentiment is strong, it is often manifested as Longs paying Shorts). It is only an emotional reference and does not predict price.

**Related terms:** Perpetual Contract, Long / Long, Short / Short

---

### 16. Long/Short Ratio

**One-sentence definition:** The Long/Short Ratio is a proportional data of Long and Short forces (based on Open Interest or account count) in the contract market.

**Detailed explanation:** Examples include "Whale Long/Short Ratio" and "Account Long/Short Ratio," reflecting the current market participants' holding bias. It is an **emotional / holding reference data** that helps observe the distribution of Long and Short forces, but **it is not a buy/sell signal and does not predict price**. Midas's Contract Dimension chart will display this type of data.

**Related terms:** Open Interest / OI, Perpetual Contract, Spot

---

### 17. Open Interest / OI

**One-sentence definition:** Open Interest (OI) refers to the total number of outstanding contracts in the market.

**Detailed explanation:** It reflects the volume of capital participating in the contract market—an increase in OI usually indicates new capital entering (new positions being established), while a decrease indicates positions being closed. It is a **reference data** for observing market participation and does not directly indicate direction or predict price movements. It is often used with the Long/Short Ratio and Funding Rate for contract analysis.

**Related terms:** Long/Short Ratio, Funding Rate, Perpetual Contract

---

### 18. Liquidation Price / Forced Close Price

**One-sentence definition:** The Liquidation Price is the price at which a position will be forcibly closed when the price moves in the opposite direction to that point.

**Detailed explanation:** When trading with leverage / contracts, the system calculates a liquidation price based on your margin, leverage, and position; once the price moves in the opposite direction to reach that level, the position is forcibly closed (liquidated). ⚠️ The higher the leverage, the closer the liquidation price is to the entry price and the easier it is to be triggered. Knowing your liquidation price is a basic skill in risk management.

**Related terms:** Liquidation / Forced Close, Margin, Leverage Multiplier

---

### 19. Cross / Isolated Margin

**One-sentence definition:** Cross and Isolated Margin are two types of margin modes for contracts, differing in how much capital backs the position.

**Detailed Explanation:** Isolated Margin—risk is assumed only by the margin allocated to that position; liquidation losses are limited to this amount and do not affect the rest of the account funds. Cross Margin—uses the account's total available balance to backstop the position, making it less likely to trigger a single-position liquidation, but once liquidated, potential losses may be greater. ⚠️ Both modes carry liquidation risks; use them cautiously after understanding them.

**Related Terms:** Margin, Maintenance Price / Liquidation Price, Leverage

---

### 20. Leverage Ratio

**One-Sentence Definition:** The leverage ratio refers to the multiple by which the position size is amplified relative to the margin, such as 5x, 10x.

**Detailed Explanation:** For example, with 10x leverage, it means using 1 unit of margin to operate a position of 10 units, and profits and losses are magnified by 10x. ⚠️ The higher the multiple, the more violent the profit and loss magnification, the smaller the adverse fluctuation it can withstand, and the closer it is to liquidation. Beginners should start with low leverage—it does not improve win rate, it only amplifies results.

**Related Terms:** Leverage, Margin, Maintenance Price / Liquidation Price

---

### 21. Unrealized PnL

**One-Sentence Definition:** Unrealized PnL refers to the book profit or loss of a position calculated at the current price before the position is closed.

**Detailed Explanation:** It is "floating profit / floating loss" and changes constantly with price fluctuations; it only becomes truly realized profit or loss **after closing the position**. Floating profit does not equal cash in hand—if prices retract, floating profit may shrink or even turn into a loss. This is also the significance of take profit: to lock floating profit into realized profit.

**Related Terms:** Open / Close Position, Take Profit, Position

---

---

### 80. Delivery / Futures Contract

**One-Sentence Definition:** A delivery contract is a contract with a clear expiration date that requires settlement/delivery upon expiration; this is its core difference from "Perpetual Contracts" (Perpetuals have no expiration date).

**Detailed Explanation:** It stipulates a future delivery date; upon expiration, it settles according to rules, and positions cannot be held indefinitely. To continue holding near expiration requires "rolling over" (switching to the next contract month). It does not have the continuous funding rate mechanism of Perpetuals (which rely on funding rates to anchor to spot prices), but rather converges to spot prices upon expiration. ⚠️ Delivery contracts also carry leverage—while amplifying gains, they **equally amplify losses and carry liquidation risks**; use caution. The two are just different contract forms, and Perpetuals are more mainstream in the crypto market.

---

### 81. Open Interest (OI) Interpretation

**One-Sentence Definition:** Open Interest (OI) is the total amount of unsettled contracts in the market; "OI Interpretation" is a reference method that combines its changes with price movements for observation.

**Detailed Explanation:** OI increase (position increase) usually means new capital has entered the market and participation has risen; OI decrease (position decrease) means capital has exited and positions have been closed. Combining it with price is a common reference interpretation (e.g., "price rises and OI increases" is often interpreted as new capital participating in the rise, while "price rises but OI decreases" may be short covering). It is used to understand whether the move is driven by new capital or the unwinding of old positions. However, these are all reference interpretations with exceptions; OI is not a buy/sell signal and does not predict price.

---

### 82. Liquidation & Negative Balance

**One-Sentence Definition:** Liquidation (margin call) is the forced closing of a position when losses approach the margin; Negative Balance is a more extreme situation—losses exceed all margin, resulting in a "negative" account balance.

**Detailed Explanation:** Normally, liquidation is triggered when losses hit the maintenance margin and the position is closed (reviewing "Liquidation Price": Longs are triggered below the open price, Shorts above). However, in extreme market conditions (sharp gaps, liquidity dry-up, excessive slippage), closing may not be completed before the margin is exhausted, leading to losses exceeding the margin, i.e., "negative balance." ⚠️ Negative balance means you may owe money; it is one of the extreme risks of high-leverage contracts—again emphasizing that high leverage = high risk. Be sure to control leverage and use strict stop-loss.

---

## Spot and Market Mechanisms

### 22. T+0 / T+1 (Trading Settlement Cycle)

**One-Sentence Definition:** T+0 refers to buying and selling on the same day; T+1 refers to buying on the current day and selling only on the next trading day.

**Detailed Explanation:** Crypto, US stocks, and HK stocks are generally T+0; A-share stocks are T+1. Note: The US stock "Day Trader (PDT) Rule" restricting small accounts from intraday trading was cancelled in June 2026 and changed to an intraday margin framework. Market rules may adjust; please refer to the official latest regulations.

**Related Terms:** Limit Up / Limit Down, Circuit Breaker, Spot

---

### 23. Circuit Breaker

**One-Sentence Definition:** A circuit breaker is a mechanism that pauses trading for a period of time to "cool down" when price fluctuations reach preset thresholds.

**Detailed Explanation:** For example, the US stock market has market-level circuit breakers based on broad index declines (reaching certain tiers) and volatility halts at the individual stock level; the HK market has a "Volatility Control Mechanism (VCM)" for certain securities. Its function is to buffer market sentiment during extreme volatility. Specific thresholds and rules should refer to the official latest regulations of each market.

**Related Terms:** Limit Up / Limit Down, T+0 / T+1, Liquidity

---

### 24. Slippage

**One-Sentence Definition:** Slippage refers to the deviation between the actual execution price and the expected price when placing an order.

**Detailed Explanation:** It is common with Market Orders, especially during severe market fluctuations or poor liquidity—there may be a gap between the price you see and the price actually executed. The better the liquidity and the more stable the market, the smaller the slippage. It is a real cost of trading and you need to anticipate it when placing orders.

**Related Terms:** Market Order, Liquidity, Order Book / Bid/Ask

---

### 25. Liquidity

**One-Sentence Definition:** Liquidity refers to the ease and low cost of buying and selling a market or instrument quickly.

**Detailed Explanation:** Good liquidity means ample buy and sell orders, easy finding of counterparties when you want to trade, small slippage, and stable prices; poor liquidity is the opposite—trading is difficult, slippage is large, and prices can be heavily moved by small orders. Mainstream instruments usually have good liquidity.

**Related Terms:** Order Book / Bid/Ask, Slippage, Market Maker

---

### 26. Spot

**One-Sentence Definition:** Spot refers to trading by buying and actually holding the asset itself to earn the price spread.

**Detailed Explanation:** Unlike contracts, in spot trading you own the underlying asset, and profit/loss comes from price changes; generally, you can only Long (Short requires borrowing), and it does not carry leverage by default, and thus no liquidation—price drops only result in unrealized losses. Compared to contracts, spot carries lower risk.

**Related Terms:** Perpetual Contract, Long / Long, Leverage

---

### 27. Market Maker

**One-Sentence Definition:** A Market Maker is a participant who simultaneously posts bid and ask prices to provide liquidity to the market.

**Detailed Explanation:** They are ready to buy or sell at any time, primarily profiting from the "bid-ask spread." The existence of market makers makes it easier for you to find counterparties when placing orders and facilitates smoother execution; they are an important source of market liquidity.

**Related Terms:** Liquidity, Order Book / Bid/Ask, Volume

---

### 28. Order Book / Bid/Ask

**One-Sentence Definition:** The Order Book (Bid/Ask / Order Book) is a list of current buy and sell orders with prices and quantities on the market.

**Detailed Explanation:** It shows the buy orders (bids) and sell orders (asks) waiting to be filled at each price level. The thicker the "Order Book" (more hanging orders), the better the liquidity and the smaller the slippage. Market orders will "eat" the best opposing hanging orders on the Order Book and execute immediately.

**Related Terms:** Liquidity, Market Maker, Market Order

---

### 29. Volume

**One-Sentence Definition:** Volume refers to the actual number of transactions completed over a period of time.

**Detailed Explanation:** It reflects market activity and participation intensity—high volume (significantly increased trading volume) indicates strong buying and selling intent, while low volume indicates a quiet market. Volume-price coordination is an important part of technical analysis (e.g., "rising volume and price"), but volume is reference information and needs to be combined with price and other factors; it does not predict rises or falls on its own.

**Related Terms:** Liquidity, Order Book / Bid/Ask, Trend

---

---

## Candlesticks and Charts

### 30. Candlestick (Candle Chart)

**One-Sentence Definition:** Candlesticks (candle charts) record price over a period of time using a single "candle," and are the most basic form of chart.

**Detailed Explanation:** Every candlestick consists of four prices: Open, Close, High, and Low. The body is formed by the open and close prices; the thin lines above and below the body are the upper and lower shadows. A close above the open is a Bullish candle; a close below the open is a Bearish candle (Midas follows A-share convention: Red for Up, Green for Down; some overseas markets are opposite). Different timeframes represent different time spans.

**Related Terms:** MA, Bollinger Bands, Fractal

---

### 31. Bullish Candle / Bearish Candle

**One-sentence Definition:** A Bullish candle refers to a candlestick where the close price is higher than the open price; a Bearish candle refers to a candlestick where the close price is lower than the open price.

**Detailed Explanation:** A Bullish candle represents an upward movement during this period, while a Bearish candle represents a downward movement. Midas follows A-share convention: Bullish candles are Red, Bearish candles are Green (some overseas markets are opposite). In a Bullish candle, the lower edge of the body is the open price and the upper edge is the close price; in a Bearish candle, it is the opposite (upper edge open, lower edge close).

**Related Terms:** Candlestick (Japanese Candlestick), Body, Shadow

---

### 32. Shadow (Upper Shadow / Lower Shadow)

**One-sentence Definition:** The shadow is the thin line extending above or below the candlestick body, recording the extreme price levels reached.

**Detailed Explanation:** The upper shadow (from the top of the body to the High) reflects that the price was pushed up and then pulled back, indicating selling pressure above; the lower shadow (from the bottom of the body to the Low) reflects that the price was pulled down and then rebounded, indicating buying support below. The longer the shadow, the more intense the battle between bulls and bears. It is a signal of the battle, not a guarantee of price direction.

**Related Terms:** Body, Bullish Candle / Bearish Candle, Hammer

---

### 33. Body (Candlestick Body)

**One-sentence Definition:** The body is the "thick" part of the candlestick formed by the open and close prices.

**Detailed Explanation:** The height of the body = the distance between the open and close prices. A large body indicates a clear direction and strong momentum during this period; a small body (like a Doji) indicates that the open and close are close, showing a stalemate between bulls and bears. The color of the body (Bullish / Bearish) indicates whether the price rose or fell during this period.

**Related Terms:** Shadow, Bullish Candle / Bearish Candle, Candlestick (Japanese Candlestick)

---

### 34. Hammer

**One-sentence Definition:** A Hammer is a candlestick pattern with a small body, a long lower shadow, and a very short or non-existent upper shadow.

**Detailed Explanation:** It resembles a hammer (small body on top, long lower shadow below), indicating that the price was pushed down significantly and then pulled back strongly by buyers. When it appears at a low level after a downtrend, it is often seen as a potential stabilization / reversal signal—but it is a reference signal requiring subsequent verification, **not a "guaranteed rise."**

**Related Terms:** Shadow, Body, Divergence

〔Suggested Image (reuse A3 Hammer Chart): A Hammer pattern with "small body on top + long lower shadow + almost no upper shadow" appearing at a low level after a downtrend, labeled "Potential stabilization signal at low levels, requires verification, not a guaranteed rise."〕

---

### 35. Timeframe

**One-sentence Definition:** A timeframe refers to the duration represented by a single candlestick, or the time scale used for analysis.

**Detailed Explanation:** Examples include 1-minute, 1-hour, and daily charts, where each candlestick represents 1 minute, 1 hour, or one day respectively. There is no "good" or "bad" timeframe: use larger timeframes for the big picture (stable) and smaller timeframes for details (sensitive). The "level" in Chan Theory is a similar concept, and its structure is recursive.

**Related Terms:** Candlestick (Japanese Candlestick), Trend, Chan Theory

---

---

### 79. Multi-Timeframe Analysis

**One-sentence Definition:** Multi-Timeframe Analysis involves observing the same asset across different timeframes (e.g., Daily, 4H, 15m) simultaneously, using "Big timeframe to determine direction, Small timeframe to find entry" for comprehensive judgment.

**Detailed Explanation:** The common approach is to first use a large timeframe (e.g., Daily) to judge the overall trend and key structures (determine direction), then move to a smaller timeframe (e.g., 15m) to find more precise entry timing and stop-loss levels (find entry). This aligns direction with entry to reduce the bias of "only looking at one timeframe and seeing only the trees, not the forest." Note that different timeframes may give conflicting signals; prioritize the large timeframe and use the small timeframe as a supplement. It is an analytical method to improve judgment comprehensiveness, not a method to eliminate misjudgments or predict the future.

---

## Technical Indicators

### 36. Moving Average (MA)

**One-sentence Definition:** The Moving Average is a line formed by connecting the average closing prices of the last N periods; it is the most basic trend indicator.

**Detailed Explanation:** For example, MA5 = the average of the last 5-day closing prices, calculated rolling. It is smoother than the price and can be approximated as the "average holding cost" during this period; an upward direction indicates a Bullish market, downward indicates a Bearish market. Short-term MAs are sensitive, long-term MAs are stable. MAs reflect **historical** trends and do not predict the future.

**Related Terms:** Golden cross / Death cross, MACD, Bollinger Bands

---

### 37. Golden Cross / Death Cross

**One-sentence Definition:** Golden Cross = Short-term line crosses above the long-term line; Death Cross = Short-term line crosses below the long-term line.

**Detailed Explanation:** Most commonly refers to the crossover of Moving Averages: Golden Cross = Short-term MA crosses above the long-term MA (Bullish reference); Death Cross = Short-term MA crosses below the long-term MA (Bearish reference). Do not get the direction reversed. MACD also has Golden and Death crosses (referring to DIF crossing above / below DEA). They are **lagging signals** and are references, not predictions. There are many false signals in ranging markets; do not trade solely based on Golden or Death crosses.

**Related Terms:** Moving Average, MACD, Bollinger Bands

---

### 38. MACD

**One-sentence Definition:** MACD is an indicator reflecting trend momentum, composed of the DIF line, DEA line, and red/green bars.

**Detailed Explanation:** DIF = Fast MA - Slow MA (commonly 12, 26); DEA = MA of DIF (commonly 9), smoother and more lagging; Red/Green bars = DIF - DEA (DIF above is positive, Red, above zero line; below is negative, Green, below zero line). MACD Golden Cross = DIF crosses above DEA; Death Cross = DIF crosses below DEA. It is a lagging indicator reflecting momentum, not predicting price.

**Related Terms:** Golden cross / Death cross, Divergence, Moving Average

---

### 39. Bollinger Bands (BOLL)

**One-sentence Definition:** Bollinger Bands are price channels constructed by taking a Moving Average as the middle band and adding/subtracting standard deviations.

**Detailed Explanation:** Middle band = Moving Average (commonly 20 periods); Upper band = Middle band + K * Standard Deviation; Lower band = Middle band - K * Standard Deviation (commonly K = 2). The width of the channel changes with volatility (Opening = increasing volatility, Closing = converging volatility). Prices mostly move within the channel; touching the upper or lower bands is a **position reference, not a reversal signal** (in strong trends, prices can run along the bands).

**Related Terms:** Moving Average, RSI, MACD

---

### 40. RSI (Relative Strength Index)

**One-sentence Definition:** RSI is an oscillator with values between 0–100, reflecting the comparison of recent buying and selling power.

**Detailed Explanation:** 50 is the center line; above 50 indicates the bullish side is dominant, below 50 indicates the bearish side is dominant. Common reference zones are >70 as Overbought and <30 as Oversold (**thresholds are not unique**). However, Overbought does not mean a drop immediately, and Oversold does not mean a rise immediately—in strong trends, RSI can "stall" and stay at extreme values for a long time. It is a reference zone, not a reversal signal.

**Related Terms:** MACD, Bollinger Bands, Divergence

---

### 41. Trend

**One-sentence Definition:** A trend is the directional movement of price, divided into three types: Uptrend, Downtrend, and Ranging.

**Detailed Explanation:** Uptrend = Higher Highs and Higher Lows; Downtrend = Lower Highs and Lower Lows; Ranging = Highs and Lows roughly flat, moving back and forth within a range. "Trade with the trend" is a common philosophy, but trends can continue and reverse. Judging a trend itself requires practice and does not predict the future.

**Related Terms:** Support, Resistance, Ranging / Consolidation

---

### 42. Support

**One-sentence Definition:** Support is an area below the price where buying pressure is concentrated, making it easy for the price to stop falling and rebound.

**Detailed Explanation:** Can be understood as the "floor" of the price. Identification clues include previous lows and dense trading areas. Note that it is a **probabilistic reference zone, not a guarantee of a rebound**—the price may rebound, or it may break directly through; once broken downward, it often transforms into resistance.

**Related Terms:** Resistance, Trend, Volume

---

### 43. Resistance

**One-sentence Definition:** Resistance is an area above the price where selling pressure is concentrated, making it easy for the price to be blocked and fall back.

**Detailed Explanation:** It can be understood as the "ceiling" of price. Identification clues include previous highs and dense trading areas. It is also a **probabilistic reference zone, not a guarantee of "resistance"**—price may pull back, or it may break out on high volume; after being broken upward, it often transforms into support.

**Related Terms:** Support, Trend, Volume

---

### 44. Consolidation / Sideways

**One-sentence Definition:** Consolidation (Sideways) refers to a state where price fluctuates back and forth within a range without a clear direction.

**Detailed Explanation:** The characteristic is that highs and lows are roughly flat, and price repeatedly moves between the resistance above and the support below. It often implies a temporary balance between long and short forces. The market spends most of its time in consolidation; in Chan Theory, the **Central Hub** corresponds to this consolidation zone.

**Related Terms:** Trend, Support, Central Hub

---

### 45. Overbought / Oversold

**One-sentence Definition:** Overbought refers to a reference zone where the uptrend is strong and prices are high; Oversold refers to a reference zone where the downtrend is strong and prices are low.

**Detailed Explanation:** Commonly measured by indicators like RSI (e.g., RSI >70 is Overbought, <30 is Oversold, thresholds are not unique). Key reminder: **Overbought does not mean an immediate drop, and Oversold does not mean an immediate rise**—in strong trends, indicators can "stagnate" and remain at extreme values for a long time. They are reference zones, not reversal signals.

**Related Terms:** RSI, Stagnation, Momentum / Strength

---

### 46. Indicator Saturation

**One-sentence Definition:** Stagnation refers to the phenomenon where an indicator becomes "ineffective" and no longer effectively signals a reversal after entering an extreme zone.

**Detailed Explanation:** Common in strong trends—for example, RSI remains in the Overbought zone (>70) for a long time while prices continue to rise; at this point, "Overbought" does not imply a drop. Stagnation reminds us: signals like Overbought/Oversold are references, not guarantees of reversal; mechanically applying them easily leads to repeated losses in strong trends.

**Related Terms:** Overbought / Oversold, RSI, Divergence

---

### 47. Divergence

**One-sentence Definition:** Divergence refers to the phenomenon where the price trend moves in the opposite direction of the technical indicator trend.

**Detailed Explanation:** Bullish Divergence = Price makes a new high (higher high) but the indicator makes a lower high; Bearish Divergence = Price makes a new low (lower low) but the indicator makes a higher low. It often signals that trend momentum is exhausted and a reversal may occur. However, Divergence is not a precise timing tool—it can stagnate, may require multiple occurrences before reversing, or may fail; it serves only as a reference. (The similar concept in Chan Theory is called **Divergence**.)

**Related Terms:** Divergence, MACD, RSI

---

### 48. Bullish / Bearish MA Alignment

**One-sentence Definition:** Refers to the strong or weak arrangement order when using multiple short / medium / long MAs simultaneously.

**Detailed Explanation:** Bullish Alignment = From top to bottom: Price > Short-term > Medium-term > Long-term (Short is on top, Price is on top), representing a strong uptrend structure; Bearish Alignment = From top to bottom: Long-term > Medium-term > Short-term > Price (Short is at the bottom, Price is at the bottom), representing a weak downtrend structure. After alignment becomes entangled, it hints that the trend may change (not inevitable, and lagging).

**Related Terms:** MA, Golden cross / Death cross, Trend

---

### 49. Standard Deviation

**One-sentence Definition:** Standard Deviation is a statistical measure of the volatility and dispersion of data (here, price).

**Detailed Explanation:** The greater the price volatility, the greater the Standard Deviation; the smaller the volatility, the smaller the Standard Deviation. Bollinger Bands use it to define the upper and lower rails: Upper/Lower Rails = Middle Rail ± K times Standard Deviation, so when volatility is high the channel widens (opens), and when volatility is low it narrows (closes).

**Related Terms:** Bollinger Bands, Open / Close, Momentum / Strength

---

### 50. EMA (Exponential Moving Average)

**One-sentence Definition:** EMA is a Moving Average that assigns higher weight to recent prices.

**Detailed Explanation:** Unlike "Simple Moving Average (SMA, where each closing price has equal weight)," EMA reacts more sensitively to recent prices and follows faster. Many indicators (such as MACD) use EMA internally. Like ordinary MAs, it reflects the existing trend and does not predict the future.

**Related Terms:** MA, MACD, Momentum / Strength

---

### 51. Open / Close (Bollinger Bands)

**One-sentence Definition:** Open refers to the Bollinger Bands upper and lower rails widening (volatility increasing), while Close refers to the upper and lower rails narrowing (volatility converging).

**Detailed Explanation:** The width of the channel is determined by Standard Deviation (volatility). A long period of closing often "brews a trend change," after which a directional breakout often arrives—but **the direction of the breakout cannot be predicted by the closing itself**; it is by no means a guarantee of a rise or a fall. It signals "volatility state," not "direction."

**Related Terms:** Bollinger Bands, Standard Deviation, Consolidation / Sideways

---

### 52. Momentum / Strength

**One-sentence Definition:** Momentum (Strength) refers to the strength of the "drive" of price movement—is it accelerating or decaying?

**Detailed Explanation:** It focuses not on the price itself, but on the force driving the price. The red and green bars of MACD, Divergence / **Divergence**, etc., are used to observe momentum: increased momentum supports trend continuation, while momentum decay (e.g., Divergence) hints that the trend may weaken. It is a reference perspective, not a prediction of precise price action.

**Related Terms:** MACD, Divergence, Divergence

---

---

### 67. KDJ (Stochastic Oscillator)

**One-sentence Definition:** KDJ is a technical indicator that measures Overbought/Oversold and Momentum by comparing the relative position of the closing price within the recent price range, composed of three lines: K, D, and J.

**Detailed Explanation:** It first calculates the relative position of the closing price between the highest and lowest prices of the recent period, smoothing to get the K and D lines, with J = 3K − 2D used to amplify volatility. Common usage involves looking at the Golden cross (K crosses above D) / Death cross (K crosses below D) of K and D, and Overbought/Oversold zones (e.g., above 80 is slightly Overbought, below 20 is slightly Oversold) as references. Like RSI, it belongs to indicators measuring Overbought/Oversold but is more sensitive to short-term volatility and generates signals more frequently; it will also "stagnate" in strong trends (Overbought can be more Overbought)—it is a reference, not a buy/sell instruction, and does not predict.

---

### 68. Difference Between SMA and EMA (Simple Moving Average SMA / Exponential Moving Average EMA)

**One-sentence Definition:** Both are MAs, with the difference being: SMA treats each price in the range "equally" when averaging, while EMA gives higher weight to recent prices.

**Detailed Explanation:** SMA (Simple Moving Average) performs a simple arithmetic average of the past N periods' prices with equal weight; EMA (Exponential Moving Average) uses exponentially decaying weights, with the closer the price, the greater the influence. The result is that EMA reacts faster to the latest changes and turns more sensitively, but is more susceptible to short-term volatility interference; SMA is smoother and more sluggish. Neither is absolutely better—use EMA for fast reaction, SMA for stability; both lag behind price and serve as trend references, not predictions.

---

### 69. Volume Indicators and Volume-Price Relationship

**One-sentence Definition:** Volume measures the number of transactions over a period of time, while "Volume-Price Relationship" is a reference method that combines volume with price changes for observation.

**Detailed Explanation:** Volume reflects the activity and intensity of market participation—usually, an uptrend / breakout accompanied by high volume indicates sufficient participating force; shrinking volume casts doubt on the strength. Common reference interpretations include "Price rises with volume increase, Price falls with volume decrease," used to indirectly judge whether there is volume support behind the trend. However, Volume-Price Relationship is only a reference, has exceptions, and does not predict; the meaning of volume also varies in different markets, so it must be viewed in conjunction with price and other information, not treated as a buy/sell signal.

---

### 70. ATR (Average True Range)

**One-sentence Definition:** ATR is an indicator that measures the "average volatility" of price, reflecting the intensity of recent market volatility (rather than direction).

**Detailed Explanation:** It first calculates the "True Range" for each candle (considering gaps by taking the larger of the day's high-low difference and the difference from the previous close), then averages it over a period. A larger ATR indicates higher volatility, while a smaller ATR indicates calmness—it only describes "how volatile" it is, not the direction of price movement. It is commonly used as a reference for setting stop-loss distances, measuring risk, and adjusting position sizes based on volatility (e.g., widening stop-losses or reducing positions during high volatility). It is a reference tool, not a price predictor.

---

### 71. Bias (BIAS)

**One-sentence definition:** Bias measures the degree to which the current price deviates from a specific Moving Average, expressed as a percentage of how far the price is from the MA.

**Detailed Explanation:** Calculated as (Current Price − MA) ÷ MA × 100%. A positive value indicates the price is above the MA, and a negative value indicates it is below; the larger the absolute value, the greater the deviation. It is often used as a reference from a "mean reversion" perspective—when Bias is excessively large, the price is considered to have a tendency to revert to the MA. However, note that a large Bias does not mean an immediate reversion; in strong trends, prices can maintain a large Bias for a long time. It is a reference, not a predictor; using Bias to go Long/Short against the trend carries high risk.

---

## Chart Patterns

### 72. Doji

**One-sentence definition:** A Doji is a candlestick pattern with an opening price very close to the closing price, an extremely small real body, and shadows on both the top and bottom, often viewed as a signal of balanced long/short power and market indecision.

**Detailed Explanation:** Because the open and close are nearly equal, the candle looks like a "cross." It typically appears during fierce competition between longs and shorts or when the direction is unclear, serving as one of the reference signals for a potential trend change (especially when appearing at the end of a trend). However, a Doji only represents "current indecision" and does not itself predict direction; it must be confirmed by position, trend, and subsequent candles. A single Doji is not a buy/sell signal and does not predict.

---

### 73. Engulfing Pattern (Bullish Engulfing / Bearish Engulfing)

**One-sentence definition:** An Engulfing pattern consists of two candles where the second candle's body completely "engulfs" the first candle's body, serving as a reversal reference pattern, divided into Bullish Engulfing and Bearish Engulfing.

**Detailed Explanation:** A Bullish Engulfing pattern appears during a decline, where the second candle's real body completely covers the previous bearish candle's real body, viewed as a reference for a counterattack by the bulls. A Bearish Engulfing pattern appears during an advance, where the second bearish candle's real body engulfs the previous bullish candle's real body, viewed as a reference for a counterattack by the bears. It is a reference signal for a "possible reversal," but it is common and not always effective—it requires confirmation with trend, position, and subsequent movement and cannot be treated as a buy/sell order based solely on one engulfing pattern; it does not predict.

---

### 74. Head and Shoulders (Head and Shoulders Top / Head and Shoulders Bottom)

**One-sentence definition:** The Head and Shoulders pattern is a classic reversal pattern composed of three fluctuations: "Left Shoulder — Head — Right Shoulder"; the Head and Shoulders Top often appears at the top, while the Head and Shoulders Bottom often appears at the bottom.

**Detailed Explanation:** The Head and Shoulders Top has three highs, with the middle "Head" being the highest and the two sides "Shoulders" lower; the line connecting the two lows is called the "Neckline," and a break below the neckline is often viewed as a reference for a top reversal. The Head and Shoulders Bottom is the vertical mirror image, and a break above the neckline is viewed as a reference for a bottom reversal. It is a widely circulated pattern, but identification is subjective and it can fail (false breakouts of the neckline are common)—it is a reference rather than a certainty, requiring confirmation and stop-losses, and does not predict.

---

### 75. Double Top / Double Bottom (M Top / W Bottom)

**One-sentence definition:** The Double Top (M Top) is a top reversal reference pattern where the price attempts to rise twice without breaking through, forming two similar highs; the Double Bottom (W Bottom) is a bottom reversal reference pattern where the price attempts to bottom out twice and recovers, forming two similar lows.

**Detailed Explanation:** The M Top resembles the letter M; the low point between the two highs forms the "Neckline," and a break below the neckline is often used as a reversal reference. The W Bottom resembles the letter W, and a break above the neckline serves as a reversal reference. They reflect "resistance or support at a certain price level." Similarly, pattern identification is subjective and can fail (false breakouts), serving only as a reference that requires confirmation and stop-losses, not constituting a buy/sell order, and does not predict.

---

### 76. Gap

**One-sentence definition:** A Gap refers to a price void that appears between adjacent candles where no trading occurred (e.g., today's low is still higher than yesterday's high), appearing on the candlestick chart as a "jump."

**Detailed Explanation:** Gaps are usually formed by news, sentiment, or opening gaps and are often classified as Common Gaps, Breakaway Gaps, Continuation Gaps, and Exhaustion Gaps (classification is subjective). The market has the saying that "gaps may be filled" (price returns to the gap area in the future), but this is only a reference observation, not a law—gaps do not necessarily fill and do not predict direction. It is a reference that requires judgment based on trend and position, not a buy/sell signal.

---

### 77. Elliott Wave Theory (Elliott Wave, Introductory Concept)

**One-sentence definition:** Elliott Wave Theory is an analytical framework proposed by Elliott, believing that price movements unfold in a cyclical wave structure of "Five Impulse Waves + Three Correction Waves" (conceptual understanding).

**Detailed Explanation:** It summarizes trend-directional movements as 5 impulse waves and corrections as 3 waves (commonly known as the 5-3 structure), with different levels of nesting. However, wave counting is highly subjective—different people may count different waves for the same market move; it is clear in hindsight but often ambiguous in the moment. It is a reference framework to help understand market rhythm, **absolutely not an accurate prediction tool**. One should not make judgments of "inevitable rise or fall" based on it and must combine it with other methods and risk management.

---

### 78. Trendlines and Channels (Trendline & Channel)

**One-sentence definition:** A Trendline is a straight line connecting a series of highs or lows to depict the trend direction; a Channel line is a parallel line drawn on the other side of the trendline, with the two forming the "channel" within which price moves.

**Detailed Explanation:** In an uptrend, a support trendline is often drawn by connecting a series of rising lows; in a downtrend, a resistance trendline is drawn by connecting a series of falling highs, and a parallel line is added to form a channel. Price touching the trendline/channel boundaries often serves as a reference observation point, and a break below the trendline may signal weakening of the trend. However, drawing trendlines is subjective (which points to connect varies by person) and can be subject to false breakouts; it is a reference rather than an exact signal and does not predict.

---

## Chan Theory

### 53. Chan Theory (Chan Zhong Shuo Chan Theory)

**One-sentence definition:** Chan Theory is an analytical system that decomposes and describes price movements using strict geometric structures.

**Detailed Explanation:** Originating from online serializations under the pen name "Chan Zhong Shuo Chan," its core is to break down movements into progressively layered structures such as Fractals, Strokes, Segments, and Central Hubs, emphasizing "Complete Classification (Trend / Consolidation)" and "Level Recursion." It is an analytical tool, not a prediction magic weapon—the system is vast, has a learning barrier, and does not predict the future or promise profits.

**Related Terms:** Fractal, Stroke, Central Hub

---

### 54. K-Line Inclusion Relationship

**One-sentence definition:** The Inclusion Relationship refers to a situation where the high-low range of one adjacent candle completely contains the other.

**Detailed Explanation:** That is, the highest point of one candle is not lower than, and the lowest point is not higher than, the other candle (the range of one completely covers the other). Chan Theory first processes inclusion relationships—taking the "higher high" upward and the "lower low" downward to merge the two candles into one, eliminating structural ambiguity to facilitate the identification of Fractals and Strokes. This is the first fundamental skill of Chan Theory.

**Related Terms:** Fractal, Stroke, Chan Theory

---

### 55. Fractal (Top Fractal / Bottom Fractal)

**One-sentence definition:** A Fractal is a structure composed of three adjacent candles (after inclusion relationships are processed) that marks a local turning point.

**Detailed Explanation:** Top Fractal = the middle candle has the highest high and the highest low (overall highest), marking a local peak; Bottom Fractal = the middle candle has the lowest low and the lowest high (overall lowest), marking a local trough. It only marks a local turning point, is of a small level, does not represent a major trend reversal, and certainly cannot be used to predict.

**Related Terms:** K-Line Inclusion Relationship, Stroke, Chan Theory

---

### 56. Stroke

**One-sentence definition:** A Stroke is the most basic unit of movement connecting an adjacent Top Fractal and Bottom Fractal.

**Detailed Explanation:** An Upward Stroke = Bottom Fractal → Top Fractal, a Downward Stroke = Top Fractal → Bottom Fractal, alternating up and down. The common bottom line for validity is that the Top and Bottom Fractals do not share candles; regarding the specific number of independent candles, there are two sets of standards—Old Stroke (at least 1 independent candle between the top and bottom, totaling at least 5 candles) and New Stroke (at least 3 independent candles between the top and bottom). A Stroke is a structural description, not a direction predictor.

**Related Terms:** Fractal, Segment, Central Hub

---

### 57. Segment

**One-sentence definition:** A Segment is a higher-level movement unit than a Stroke, composed of at least three consecutive Strokes.

**Detailed Explanation:** It requires an overlap between the Strokes; in an upward Segment, the first and third Stroke must share a price range. Segments are smoother and more stable than Strokes, reflecting the recursive structure of Chan Theory. When a Segment is effectively broken, a reverse Segment begins; precise division uses advanced criteria such as the Feature Sequence.

**Related Terms:** Stroke, Central Hub, Chan Theory

---

### 58. Central Hub

**One-sentence Definition:** A Central Hub is the overlapping interval of three consecutive lower-level trends; it is the core concept of Chan Theory.

**Detailed Explanation:** The upper boundary of a Central Hub = the **lowest** of the three trend highs; the lower boundary = the **highest** of the three trend lows (i.e., the boundaries of their common overlap). It represents a consolidation area where long and short forces are roughly balanced. It undergoes formation, extension, and renewal, and has different levels. If the three segments do not have a common overlap, they do not constitute a Central Hub.

**Related Terms:** Segment, Chan Theory Buy/Sell Points, Divergence

---

### 59. Divergence

**One-sentence Definition:** Divergence is a Chan Theory term referring to a situation where the strength of a later segment in a trend is significantly weaker than the preceding segment in the same direction.

**Detailed Explanation:** It manifests as price creating a new high / new low, but the driving force (momentum) weakens. Its meaning is similar to "momentum exhaustion" and is often measured using tools like MACD (Chan Theory also combines trend levels and Central Hubs for stricter judgment). Divergence is an important basis for judging potential trend reversals (such as the First Type Buy/Sell Point), but it is a reference point, not a prediction of the exact timing; it may also stagnate or fail.

**Related Terms:** MACD, Chan Theory Buy/Sell Points, Central Hub

---

### 60. Chan Theory Buy/Sell Points (Three Types of Buy/Sell Points)

**One-sentence Definition:** Chan Theory Buy/Sell Points are terms describing the **structural position** of a trend; ★ they are **not** "orders to buy or sell."

**Detailed Explanation:** First Type = The turning point after a trend Divergence; Second Type = After the First Type, a pullback fails to break the previous low (Sell Point = fails to break previous high); Third Type = After a Central Hub is broken, a pullback fails to re-enter the Central Hub. They only mark structural positions; they **do not constitute trading instructions, do not predict, and do not guarantee profits**—even at a "Buy Point," the price may continue to fall, so risk management must be paired with it.

**Related Terms:** Divergence, Central Hub, Chan Theory

---

---

## Strategies and Arbitrage

### 83. Grid Trading

**One-sentence Definition:** Grid Trading is a strategy that places buy and sell orders at fixed intervals within a price range, mechanically selling high and buying low (buying every time it drops a grid, selling every time it rises a grid).

**Detailed Explanation:** In a sustained consolidation market, it can continuously execute trades and accumulate small spreads from grid to grid, appearing to "earn money automatically." ⚠️ But its fatal weakness is a one-way trend: in a one-way drop, it keeps buying, getting deeper into the drawdown (depleting funds); in a one-way rise, it sells too early, missing out on the big trend—the profit/loss ratio is extremely asymmetric (small wins, big losses); adding leverage to run a grid in contracts can lead to direct Liquidation in a one-way trend. It is **absolutely not a "lying flat and earning" tool**; it is only relatively controllable under sustained consolidation + strict total position control + zero/ultra-low leverage + stop-loss set at breakout of the range, and does not guarantee profits.

---

### 84. Martingale

**One-sentence Definition:** Martingale is a betting mindset that attempts to recover losses and profit by doubling the position after every loss, hoping for a rebound.

**Detailed Explanation:** ⚠️ This entry serves only as a risk warning: It has a fatal mathematical dead end—theoretically requiring "infinite capital" to withstand consecutive unfavorable markets, while real capital is limited. As long as a sufficiently long one-way trend is encountered, the position size that doubles and doubles will rapidly expand to an unmanageable level, leading to catastrophic drawdowns and Liquidation; in the long run, it will almost certainly encounter a disaster during a consecutive series of losses. It is **absolutely not a usable "strategy," but a bomb that will explode sooner or later**; it is strongly not recommended for anyone to use (this entry does not elaborate on its specific methods). If you see claims of "doubling after a loss, guaranteed profit," please be highly vigilant.

---

### 85. Arbitrage

**One-sentence Definition:** Arbitrage generally refers to a neutral strategy concept of profiting from price differences between related markets/instruments by simultaneously executing opposite operations.

**Detailed Explanation:** For example, in crypto, "Spot + Contract Hedge to eat Funding Rates" is a simplified arbitrage idea (direction is hedged away, only earning the rate). ⚠️ But "Arbitrage" is **by no means equal to "risk-free"**: it swaps directional risk for a basket of other risks—basis fluctuation risk, contract leg Liquidation risk (once a leg is Liquidated, the hedge is broken, which is the most fatal), funding rate/difference reversal risk, transaction costs (fees/slippage eat into thin profits), liquidity risk, etc. It is a concept of a neutral strategy; returns are often thin while risks are real; it is not a guaranteed profit tutorial and does not constitute operational advice.

---

### 86. Left-side / Right-side Trading

**One-sentence Definition:** Divided by the turning point, Left-side Trading is positioning before the turning point is confirmed (counter-trend, catching bottoms/tops), while Right-side Trading is entering after the turning point is confirmed (trend-following, following).

**Detailed Explanation:** Left-side costs may be better (close to the turning point), but it is easy to "catch a falling knife"—you think you see the bottom, but the price only drops to the halfway point and continues falling; Right-side has higher certainty (waiting for the trend to be confirmed), but it sacrifices the profit of the initial segment and may encounter fake breakouts. ⚠️ "Catching bottoms" in a downtrend carries extremely high risk; moreover, **no method can precisely catch the lowest point or escape the highest point** (tops and bottoms are only known after the fact). Both are trade-offs between risk and return with no absolute superiority, but for beginners, Right-side is usually safer, and regardless of left or right side, stop-loss must be paired with it, and the turning point should not be predicted.

---

## Risk and Mindset

### 61. Virtual Trading / Paper Trading

**One-sentence Definition:** Virtual Trading refers to using simulated funds to fully experience the trading process, involving no real capital profit or loss.

**Detailed Explanation:** It is a "practice field" with zero real risk; its value lies in trial and error, honing judgment, and low-cost verification of ideas. The correct usage is a serious loop of "Learn → Practice → Review," the key is to practice virtual trading as if it were a real account. Midas is an analysis terminal for full virtual trading.

**Related Terms:** Position, Risk Management, Review

---

### 62. Risk Management

**One-sentence Definition:** Risk Management refers to controlling the risk of every trade and the overall account within an acceptable range through means such as Stop Loss and position control.

**Detailed Explanation:** It is one of the most important parts of trading; the core is "control losses, stay alive"—even with great analysis, without risk management, you may be eliminated by a single large loss. Common means include setting Stop Loss, controlling single-investment amount, and not overusing leverage. It does not guarantee profits, but it can control losses.

**Related Terms:** Stop Loss, Position Management, Liquidation Price

---

### 63. Position Management

**One-sentence Definition:** Position Management refers to deciding how much capital to invest and what position size to use for each trade.

**Detailed Explanation:** It is one of the core parts of Risk Management—the consequences of being wrong once are vastly different between heavy and light positions. Reasonable position management allows you to keep losses controllable on a single trade and not suffer a crippling blow. It is often paired with Stop Loss: calculating reasonable position size based on the Stop Loss distance.

**Related Terms:** Risk Management, Stop Loss, Position

---

### 64. Review (Trade Review)

**One-sentence Definition:** Review refers to the process of reviewing a trade after it is executed, summarizing what was right and wrong, and the lessons learned.

**Detailed Explanation:** It must answer: what did I do right, what did I do wrong, was it a judgment error or an execution error (e.g., failing to maintain discipline)? Then bring these conclusions back to the next trade. It is the key to a trader's continuous improvement, especially when paired with virtual trading practice, forming a loop of "Learn → Practice → Review."

**Related Terms:** Virtual Trading / Paper Trading, Risk Management, Position Management

---

### 65. Trend Following

**One-sentence Definition:** Trend Following is a strategy concept of trading in the direction of an already confirmed trend.

**Detailed Explanation:** It does not predict tops or bottoms but follows after the trend forms and exits when the trend reverses; the core is "cutting losses short and letting profits run." It performs relatively well when there is a clear trend but easily suffers repeated Stop Losses in frequent consolidation. No strategy guarantees profits and must be paired with Risk Management.

**Related Terms:** Trading with the Trend, Trend, Risk Management

---

### 66. Trading with the Trend

**One-sentence Definition:** Trading with the Trend refers to making the operation direction as consistent as possible with the current trend direction, rather than resisting against the trend.

**Detailed Explanation:** The logic is to follow the direction of the dominant force, which typically offers higher win rates and lower resistance. However, this does not equal "the trend must continue"—trends can reverse. Therefore, even when trading with the trend, you must use stop-losses to leave room for being wrong. It is a concept for improving probability, not a guaranteed formula, and certainly does not predict the future.

**Related Terms:** Trend Following, Trend, Risk Management

---

### 87. Max Drawdown (MDD)

**One-sentence definition:** Max Drawdown refers to the maximum decline from a peak to a subsequent trough for an account (or a strategy's net value), measuring "how much was lost during the hardest times."

**Detailed Explanation:** It is a key metric for measuring risk, especially "psychological tolerance"—a strategy with high cumulative returns but a large Max Drawdown (e.g., a mid-course drawdown of over half) may likely cause you to give up during live trading. Therefore, when evaluating a strategy/account, do not look at returns alone; you must also look at Max Drawdown (when reviewing backtests, "look at the whole picture, especially paying attention to drawdown and risk-reward ratio"). The smaller the drawdown and the more stable the returns, the more likely you are to persist in the long run.

---

### 88. Overfitting

**One-sentence definition:** Overfitting occurs when rules are excessively fitted to the details of a specific historical period during backtesting/optimization, making them prone to failure on future or new data.

**Detailed Explanation:** A typical manifestation is repeatedly adjusting parameters until the backtest results look "very beautiful"—but this often just memorizes the "noise" of history rather than true patterns, revealing its true colors when facing unseen market conditions. ⚠️ The more beautiful the backtest that looks unreal, the more suspicious it is of overfitting. Like "Survivorship Bias" (backtesting only on surviving assets and overestimating performance), it is a common backtesting trap. It reminds us: **Backtesting being effective does not mean it will be effective in the future**. Backtesting is a tool to weed out bad strategies and understand characteristics, not a guarantee of future profitability.

---

---

> This dictionary contains 88 entries and is continuously expanding. Related terms for each entry facilitate cross-referencing; complete explanations of technical indicators and Chan Theory can be found in the long articles of Training Camp Groups B and C. This dictionary is a condensed query version with consistent terminology.
