import os
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import json

# Page Configuration
st.set_page_config(
    page_title="Trade Bot Dashboard",
    layout="wide",
    page_icon="📈"
)

# Page Auto-Refresh (Every 5 seconds)
st_autorefresh(interval=5 * 1000, key="data_refresh")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_PATH = os.path.join(CURRENT_DIR, "data", "trades.csv")
NEWS_PATH = os.path.join(CURRENT_DIR, "data", "news_history.csv")
REC_PATH = os.path.join(CURRENT_DIR, "data", "ai_recommendation.json")


def load_data(file_path):
    """Safely load CSV data, skipping corrupted lines."""
    if os.path.exists(file_path):
        try:
            return pd.read_csv(file_path, on_bad_lines='skip')
        except Exception as e:
            st.error(f"Error loading {file_path}: {e}")
            return pd.DataFrame()
    return pd.DataFrame()


def main():
    trades_df = load_data(TRADES_PATH)
    news_df = load_data(NEWS_PATH)

    if trades_df.empty:
        st.info("📈 **Waiting for the first trade!** The robot is currently accumulating price history and analyzing RSS feeds. Statistics will appear here once the first trade is completed.")

    # Metrics Section
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if not trades_df.empty and "balance" in trades_df.columns:
            current_balance = trades_df["balance"].iloc[-1]
        elif not trades_df.empty and "pnl" in trades_df.columns:
            current_balance = 69547.22 + trades_df["pnl"].sum()
        else:
            current_balance = 69547.22
        st.metric("Current Balance", f"${current_balance:.2f} USDT")
        
    with col2:
        if not trades_df.empty and "btc_position" in trades_df.columns:
            btc_position = trades_df["btc_position"].iloc[-1]
        elif not trades_df.empty and "qty" in trades_df.columns:
            btc_position = trades_df["qty"].iloc[-1]
        else:
            btc_position = 0.0
        st.metric("BTC Position", f"{btc_position:.4f} BTC")
        
    with col3:
        if not trades_df.empty and "balance" in trades_df.columns:
            pnl = trades_df["balance"].iloc[-1] - trades_df["balance"].iloc[0]
        elif not trades_df.empty and "pnl" in trades_df.columns:
            pnl = trades_df["pnl"].sum()
        else:
            pnl = 0.0
        st.metric("Total PnL", f"${pnl:.2f}", delta=f"{pnl:.2f}" if pnl != 0 else None)
        
    with col4:
        total_trades = len(trades_df) if not trades_df.empty else 0
        if not trades_df.empty and "result" in trades_df.columns:
            win_rate = (trades_df["result"] == "WIN").mean()
        elif not trades_df.empty and "pnl" in trades_df.columns:
            win_rate = (trades_df["pnl"] > 0).mean()
        else:
            win_rate = 0.0
        st.metric("Trades/Win Rate", f"{total_trades} trades", f"{win_rate:.1%}")

    st.markdown("---")

    # Balance Curve Chart
    st.subheader("Balance Curve")
    if not trades_df.empty and "balance" in trades_df.columns:
        st.line_chart(trades_df.set_index("timestamp")["balance"])
    elif not trades_df.empty and "pnl" in trades_df.columns:
        trades_df_sorted = trades_df.copy()
        if "exit_timestamp" in trades_df_sorted.columns:
            trades_df_sorted = trades_df_sorted.sort_values(by="exit_timestamp")
            trades_df_sorted["cumulative_balance"] = 69547.22 + trades_df_sorted["pnl"].cumsum()
            st.line_chart(trades_df_sorted.set_index("exit_timestamp")["cumulative_balance"])
    else:
        st.warning("No balance data available yet. Waiting for trades...")

    st.markdown("---")

    # Tabs Section
    tab1, tab2 = st.tabs(["News Feed", "Trade History"])

    with tab1:
        st.subheader("Latest News")
        if not news_df.empty:
            styled_df = news_df.tail(10).copy()
            if "verdict" in styled_df.columns:
                styled_df['verdict'] = styled_df['verdict'].apply(
                    lambda x: 'background-color: green' if x in ["EXCLUSIVE_POSITIVE", "POSITIVE", "ПОЗИТИВ"] else 
                              'background-color: red' if x in ["EXCLUSIVE_NEGATIVE", "NEGATIVE", "НЕГАТИВ"] else ''
                )
            st.dataframe(styled_df, width='stretch')
        else:
            st.warning("No news data available in news_history.csv")

        # AI Recommendation Section
        st.subheader("AI Recommendation")
        
        rec_loaded = False
        if os.path.exists(REC_PATH):
            try:
                with open(REC_PATH, "r", encoding="utf-8") as f:
                    rec_data = json.load(f)
                verdict_val = rec_data.get("verdict", "NEUTRAL")
                rec_text = rec_data.get("recommendation", "")
                news_title = rec_data.get("news_title", "")
                
                st.markdown(f"**Event for analysis:** *{news_title}*")
                if verdict_val in ["EXCLUSIVE_POSITIVE", "POSITIVE", "ПОЗИТИВ"]:
                    st.success(f"**{verdict_val}** — {rec_text}")
                elif verdict_val in ["EXCLUSIVE_NEGATIVE", "NEGATIVE", "НЕГАТИВ"]:
                    st.error(f"**{verdict_val}** — {rec_text}")
                else:
                    st.info(f"**{verdict_val}** — {rec_text}")
                rec_loaded = True
            except Exception as e:
                st.error(f"Error loading recommendation from JSON: {e}")
                
        if not rec_loaded:
            if not trades_df.empty and "recommendation" in trades_df.columns:
                last_trade = trades_df.dropna(subset=["recommendation"]).iloc[-1]
                verdict_val = last_trade.get("verdict", "NEUTRAL")
                rec_text = last_trade["recommendation"]
                if verdict_val in ["EXCLUSIVE_POSITIVE", "POSITIVE", "ПОЗИТИВ"]:
                    st.success(f"**{verdict_val}** — {rec_text}")
                elif verdict_val in ["EXCLUSIVE_NEGATIVE", "NEGATIVE", "НЕГАТИВ"]:
                    st.error(f"**{verdict_val}** — {rec_text}")
                else:
                    st.info(f"**{verdict_val}** — {rec_text}")
            else:
                st.info("No AI recommendations yet. Waiting for the first news item or bot express analysis...")

    with tab2:
        st.subheader("Trade History")
        if not trades_df.empty:
            df_display = trades_df.copy()
            if "exit_timestamp" in df_display.columns:
                df_display = df_display.sort_values(by="exit_timestamp", ascending=False)
            st.dataframe(df_display, width='stretch')
        else:
            st.warning("No trade data available in trades.csv")


if __name__ == "__main__":
    main()