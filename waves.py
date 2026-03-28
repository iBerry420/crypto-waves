import ccxt
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import argparse

VERSION = "1.3.0"

def get_candles(symbol="ETH/USDT", timeframe="4h", limit=300, sma=50, ema=50):
    exchange = ccxt.cryptocom({
        'enableRateLimit': True,
    })

    print(f"Fetching {limit} {timeframe} candles for {symbol}...\n")
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['x_num'] = mdates.date2num(df['timestamp'])

    df[f'SMA_{sma}'] = df['close'].rolling(sma).mean()
    df[f'EMA_{ema}'] = df['close'].ewm(span=ema).mean()

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))

    return df


def detect_crossovers(df, sma_col, ema_col):
    df = df.copy()
    df['SMA_above_EMA'] = df[sma_col] > df[ema_col]
    df['cross'] = df['SMA_above_EMA'].diff()

    crossovers = df[df['cross'] != 0].copy()

    if crossovers.empty:
        return "No recent SMA/EMA crossover"

    latest_cross = crossovers.iloc[-1]
    cross_date = latest_cross['timestamp'].strftime('%Y-%m-%d %H:%M')
    cross_price = round(latest_cross['close'], 2)
    cross_type = "BULLISH" if latest_cross['cross'] == True else "BEARISH"

    return (f"{cross_type} CROSSOVER on {cross_date} @ ${cross_price}\n")


def find_zigzag_points(df, deviation_percent=9.8):
    points = []
    last_pivot_idx = 0
    last_pivot_price = df['close'].iloc[0]
    direction = 0

    for i in range(1, len(df)):
        curr_high = df['high'].iloc[i]
        curr_low = df['low'].iloc[i]

        if direction >= 0:
            if curr_high > last_pivot_price:
                last_pivot_price = curr_high
                last_pivot_idx = i
            elif (last_pivot_price - curr_low) / last_pivot_price * 100 >= deviation_percent:
                points.append({'timestamp': df['timestamp'].iloc[last_pivot_idx], 'price': round(last_pivot_price, 2), 'type': 'HIGH'})
                last_pivot_price = curr_low
                last_pivot_idx = i
                direction = -1
        else:
            if curr_low < last_pivot_price:
                last_pivot_price = curr_low
                last_pivot_idx = i
            elif (curr_high - last_pivot_price) / last_pivot_price * 100 >= deviation_percent:
                points.append({'timestamp': df['timestamp'].iloc[last_pivot_idx], 'price': round(last_pivot_price, 2), 'type': 'LOW'})
                last_pivot_price = curr_high
                last_pivot_idx = i
                direction = 1

    points.append({'timestamp': df['timestamp'].iloc[-1], 'price': round(df['close'].iloc[-1], 2), 'type': 'CURRENT'})
    return points


# ====================== CLI ======================
def main():
    parser = argparse.ArgumentParser(
        description="Crypto Wave Pattern Analyzer",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--symbol', default='ETH/USDT', help='Trading pair (default: ETH/USDT)')
    parser.add_argument('--timeframe', default='4h', help='Timeframe: 1h, 4h, 1d, etc.')
    parser.add_argument('--deviation', type=float, default=9.8, help='ZigZag deviation %%')
    parser.add_argument('--limit', type=int, default=300)
    parser.add_argument('--sma', type=int, default=50, help='SMA period (default: 50)')
    parser.add_argument('--ema', type=int, default=50, help='EMA period (default: 50)')
    parser.add_argument('--mode', choices=['line', 'candles', 'wave'], default='line',
                        help='Chart mode:\n  line    = price line + wave\n  candles = candlesticks + wave\n  wave    = ultra clean wave only')
    parser.add_argument('--text-only', action='store_true', help='Print analysis to terminal only, skip chart')
    parser.add_argument('--save-only', action='store_true', help='Save chart without displaying window')
    parser.add_argument('-v', '--version', action='version', version=f'Crypto Wave Analyzer v{VERSION}')

    args = parser.parse_args()

    sma_col = f'SMA_{args.sma}'
    ema_col = f'EMA_{args.ema}'

    df = get_candles(args.symbol, args.timeframe, args.limit, args.sma, args.ema)
    wave_points = find_zigzag_points(df, args.deviation)

    labels = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    for i, p in enumerate(wave_points):
        p['label'] = labels[i] if i < 26 else f'P{i+1}'

    # === TECHNICAL ANALYSIS ===
    latest = df.iloc[-1]
    crossover_status = detect_crossovers(df, sma_col, ema_col)
    current_date = latest['timestamp'].strftime('%Y-%m-%d %H:%M')

    print(f"\n=== {args.symbol} {args.timeframe} ANALYSIS ===")
    print(f"Current Date      : {current_date}")
    print(f"Current Price     : ${latest['close']:.2f}")
    print(f"RSI 14            : {latest['RSI_14']:.1f}")
    print(f"SMA {args.sma:<3}           : ${latest[sma_col]:.2f}")
    print(f"EMA {args.ema:<3}           : ${latest[ema_col]:.2f}")
    print(f"Crossover Status  : {crossover_status}")
    print(f"ZigZag Deviation  : {args.deviation}% → {len(wave_points)} points\n")

    print("WAVE POINTS:")
    for p in wave_points:
        print(f"{p['label']:2} → {p['price']:10} ({p['type']:7})")

    wave_str = f"{args.symbol} {args.timeframe} wave: " + " → ".join([f"{p['label']}={p['price']}" for p in wave_points])
    print("\nAI One-liner:")
    print(wave_str)

    # ====================== CHART ======================
    if not args.text_only:
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(16, 9))

        if args.mode == "candles":
            from matplotlib.patches import Rectangle
            for i in range(len(df)):
                x = df['x_num'].iloc[i]
                o, h, l, c = df[['open','high','low','close']].iloc[i]
                color = '#00ff88' if c >= o else '#ff4444'
                ax.plot([x, x], [l, h], color='white', linewidth=1.0, alpha=0.6)
                ax.add_patch(Rectangle((x - 0.25, min(o,c)), 0.5, abs(c-o), facecolor=color, edgecolor=color, linewidth=0.8))
        elif args.mode == "line":
            ax.plot(df['x_num'], df['close'], label='Close Price', color='#00ffcc', linewidth=2.3, alpha=0.85)

        if args.mode != "wave":
            ax.plot(df['x_num'], df[sma_col], label=f'SMA {args.sma}', color='#ffaa00', linewidth=1.6)
            ax.plot(df['x_num'], df[ema_col], label=f'EMA {args.ema}', color='#ff00ff', linewidth=1.6)

        # Wave line
        wave_x = [mdates.date2num(p['timestamp']) for p in wave_points]
        wave_y = [p['price'] for p in wave_points]
        ax.plot(wave_x, wave_y, color='#00ffff', linewidth=2.6, alpha=0.95, label='ZigZag Wave')

        # Points + labels
        for i, p in enumerate(wave_points):
            color = '#ffff00' if p['type'] == 'CURRENT' else '#00ff00' if p['type'] == 'HIGH' else '#ff0000'
            ax.scatter(wave_x[i], p['price'], color=color, s=180, zorder=5, edgecolors='white', linewidth=2)
            ax.annotate(f"{p['label']} {p['price']}",
                        xy=(wave_x[i], p['price']),
                        xytext=(0, 32 if p['type'] in ['HIGH','CURRENT'] else -40),
                        textcoords='offset points',
                        fontsize=14, fontweight='bold', color=color, ha='center',
                        bbox=dict(boxstyle="round,pad=0.5", facecolor='#1a1a1a', alpha=0.95))

        mode_name = "Ultra Clean Wave" if args.mode == "wave" else "Candlesticks" if args.mode == "candles" else "Line + Wave"
        ax.set_title(f'{args.symbol} {args.timeframe} - {mode_name} | {args.deviation}% ZigZag', fontsize=16, pad=20)
        ax.set_xlabel('Date')
        ax.set_ylabel('Price (USDT)')
        ax.grid(True, alpha=0.25, color='#333333')
        ax.legend(loc='upper left', fontsize=11)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.xticks(rotation=30)

        filename = f"{args.symbol.replace('/','_')}_{args.timeframe}_{args.mode}.png"
        plt.tight_layout()
        plt.savefig(filename, dpi=350, bbox_inches='tight')
        print(f"\n✅ Chart saved as: {filename}")

        if not args.save_only:
            plt.show()


if __name__ == "__main__":
    main()