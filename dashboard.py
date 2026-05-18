"""
Real-Time Stock Sentiment Dashboard
Run: python dashboard.py  ->  http://localhost:8050
"""
import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

import store, scheduler, pricer, sentiment as sent
from config import (DEFAULT_TICKERS, TICKER_NAMES, REFRESH_INTERVAL_S,
                    BG, CARD_BG, BORDER, TEXT, MUTED, ACCENT, GREEN, RED, YELLOW)

# ── Start background data refresh ─────────────────────────────────────────────
scheduler.start(DEFAULT_TICKERS)

# ── Plotly base layout ─────────────────────────────────────────────────────────
PL = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#0d0d20",
    font=dict(color=TEXT, family="Inter, system-ui, sans-serif"),
    margin=dict(l=50, r=30, t=44, b=40),
)

# ── UI helpers ─────────────────────────────────────────────────────────────────
def card(children, extra=None):
    s = {"background": CARD_BG, "border": f"1px solid {BORDER}",
         "borderRadius": "16px", "padding": "20px"}
    if extra:
        s.update(extra)
    return html.Div(children, style=s)


def badge(label: str, color: str) -> html.Span:
    return html.Span(label, style={
        "background": color + "22", "color": color,
        "border": f"1px solid {color}44",
        "borderRadius": "6px", "padding": "2px 8px",
        "fontSize": "0.72rem", "fontWeight": "700",
        "letterSpacing": "0.04em",
    })


def sentiment_badge(label: str) -> html.Span:
    return badge(label, sent.label_color(label))


def kpi(label, value, color=ACCENT):
    return html.Div([
        html.Div(value, style={"fontSize": "2rem", "fontWeight": "800",
                               "color": color, "lineHeight": "1.1"}),
        html.Div(label, style={"fontSize": "0.7rem", "color": MUTED,
                               "textTransform": "uppercase",
                               "letterSpacing": "0.05em", "marginTop": "4px"}),
    ], style={"background": CARD_BG, "border": f"1px solid {BORDER}",
              "borderRadius": "12px", "padding": "16px 20px",
              "textAlign": "center", "flex": "1", "minWidth": "130px"})


def ticker_dd(id_, value, multi=False):
    opts = [{"label": f"{t}  —  {TICKER_NAMES.get(t, t)}", "value": t}
            for t in DEFAULT_TICKERS]
    return dcc.Dropdown(id=id_, options=opts, value=value,
                        multi=multi, clearable=False,
                        className="ipl-dropdown",
                        style={"marginBottom": "4px"})


# ── Stock card (Live Feed tab) ─────────────────────────────────────────────────
def stock_card(ticker: str, quote: dict, sentiment_row: pd.Series | None):
    price   = quote.get("price", "—")
    pct     = quote.get("pct_change", 0)
    chg     = quote.get("change", 0)
    p_color = GREEN if pct >= 0 else RED
    p_sign  = "+" if pct >= 0 else ""

    compound = float(sentiment_row["avg_compound"]) if sentiment_row is not None else 0.0
    n        = int(sentiment_row["n_headlines"])    if sentiment_row is not None else 0

    # Determine label directly from compound score
    if compound >= 0.25:
        s_label, s_color = "Bullish",          GREEN
    elif compound >= 0.05:
        s_label, s_color = "Slightly Bullish",  "#86efac"
    elif compound <= -0.25:
        s_label, s_color = "Bearish",           RED
    elif compound <= -0.05:
        s_label, s_color = "Slightly Bearish",  "#fca5a5"
    else:
        s_label, s_color = "Neutral",           MUTED

    bar_pct = int((compound + 1) / 2 * 100)    # map -1..1 → 0..100%

    return html.Div([
        html.Div([
            html.Span(ticker, style={"fontWeight": "800", "fontSize": "1.1rem"}),
            html.Span(TICKER_NAMES.get(ticker, ""), style={"color": MUTED,
                      "fontSize": "0.72rem", "marginLeft": "6px"}),
        ], style={"marginBottom": "8px"}),

        html.Div([
            html.Span(f"${price:,.2f}" if isinstance(price, float) else f"${price}",
                      style={"fontWeight": "700", "fontSize": "1.25rem"}),
            html.Span(f"  {p_sign}{pct:.2f}%",
                      style={"color": p_color, "fontWeight": "600",
                             "fontSize": "0.85rem", "marginLeft": "6px"}),
        ], style={"marginBottom": "10px"}),

        # Sentiment bar
        html.Div([
            html.Div(style={
                "height": "6px", "borderRadius": "3px",
                "background": f"linear-gradient(to right, {s_color} {bar_pct}%, rgba(255,255,255,0.06) {bar_pct}%)",
            }),
        ], style={"marginBottom": "6px"}),

        html.Div([
            badge(s_label, s_color),
            html.Span(f"  {compound:+.3f}  ·  {n} headlines",
                      style={"color": MUTED, "fontSize": "0.7rem", "marginLeft": "6px"}),
        ]),
    ], style={
        "background": CARD_BG, "border": f"1px solid {BORDER}",
        "borderRadius": "14px", "padding": "16px",
        "flex": "1", "minWidth": "190px", "cursor": "default",
        "transition": "border-color 0.2s",
    })


# ── Charts ─────────────────────────────────────────────────────────────────────
def fig_sentiment_price(ticker: str, days: int = 30):
    prices  = store.get_prices(ticker, days=days)
    daily_s = store.get_daily_sentiment(ticker, days=days)

    if prices.empty:
        return go.Figure(layout={**PL, "title": {"text": "No price data yet — fetching…", "x": 0.5}})

    # Row 1 has secondary_y for sentiment overlay; row 2 is volume
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.04,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )
    fig.add_trace(go.Candlestick(
        x=prices["date"],
        open=prices["open"], high=prices["high"],
        low=prices["low"],   close=prices["close"],
        name="Price",
        increasing_line_color=GREEN, decreasing_line_color=RED,
        increasing_fillcolor="rgba(34,197,94,0.33)",
        decreasing_fillcolor="rgba(239,68,68,0.33)",
    ), row=1, col=1, secondary_y=False)

    # Volume bars
    vol_colors = [GREEN if c >= o else RED
                  for c, o in zip(prices["close"], prices["open"])]
    fig.add_trace(go.Bar(
        x=prices["date"], y=prices["volume"],
        name="Volume", marker_color=vol_colors,
        opacity=0.5, showlegend=False,
    ), row=2, col=1)

    # Sentiment overlay on price chart (secondary y-axis)
    if not daily_s.empty:
        merged = pd.merge(prices[["date", "close"]],
                          daily_s, on="date", how="left")
        merged["avg_sentiment"] = merged["avg_sentiment"].ffill()

        bar_colors = [GREEN if v >= 0.05 else (RED if v <= -0.05 else MUTED)
                      for v in merged["avg_sentiment"].fillna(0)]
        fig.add_trace(go.Bar(
            x=merged["date"], y=merged["avg_sentiment"],
            name="Avg Sentiment", marker_color=bar_colors,
            opacity=0.65,
        ), row=1, col=1, secondary_y=True)

        # Compute correlation
        clean = merged.dropna(subset=["avg_sentiment"])
        if len(clean) >= 5:
            corr = clean["close"].corr(clean["avg_sentiment"])
            corr_label = f"r = {corr:.2f}"
        else:
            corr_label = "r = N/A"
    else:
        corr_label = "No sentiment data yet"

    name = TICKER_NAMES.get(ticker, ticker)
    fig.update_layout(
        **PL,
        height=520,
        title=dict(text=f"{ticker} — {name}  ·  {corr_label} sentiment/price correlation",
                   x=0.5),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_yaxes(title_text="Price (USD)", showgrid=True,
                     gridcolor="rgba(255,255,255,0.05)",
                     row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Sentiment", range=[-1, 1], showgrid=False,
                     zeroline=True, zerolinecolor="rgba(255,255,255,0.2)",
                     row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Volume", showgrid=False, row=2, col=1)
    return fig


def fig_leaderboard(summary: pd.DataFrame):
    if summary.empty:
        return go.Figure(layout={**PL, "title": {"text": "No data yet", "x": 0.5}})
    df = summary.sort_values("avg_compound", ascending=True)
    colors = [GREEN if v >= 0.05 else (RED if v <= -0.05 else MUTED)
              for v in df["avg_compound"]]
    fig = go.Figure(go.Bar(
        x=df["avg_compound"], y=df["ticker"],
        orientation="h", marker_color=colors,
        text=[f"{v:+.3f}  ({int(n)} articles)" for v, n in
              zip(df["avg_compound"], df["n_headlines"])],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Sentiment: %{x:.3f}<br>%{text}<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color="rgba(255,255,255,0.25)", dash="dash"))
    fig.update_layout(
        **PL, height=480,
        title=dict(text="24h Sentiment Leaderboard", x=0.5),
        xaxis=dict(showgrid=False, showticklabels=False, range=[-0.7, 0.9]),
        yaxis=dict(showgrid=False),
    )
    return fig


def fig_earnings_sentiment(ticker: str):
    df = store.get_daily_sentiment(ticker, days=30)
    if df.empty:
        return go.Figure(layout={**PL, "title": {"text": "No sentiment data yet", "x": 0.5}})
    colors = [GREEN if v >= 0.05 else (RED if v <= -0.05 else MUTED)
              for v in df["avg_sentiment"]]
    fig = go.Figure(go.Bar(
        x=df["date"], y=df["avg_sentiment"],
        marker_color=colors,
        text=[f"{v:+.3f}" for v in df["avg_sentiment"]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Sentiment: %{y:.3f}<br>%{customdata} articles<extra></extra>",
        customdata=df["n_headlines"],
    ))
    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.2)", dash="dash"))
    fig.update_layout(
        **PL, height=280,
        title=dict(text=f"{ticker} — Daily Sentiment (30 days)", x=0.5),
        xaxis=dict(showgrid=False, tickangle=-45, type="category"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                   zeroline=False),
    )
    return fig


# ── App layout ─────────────────────────────────────────────────────────────────
TAB_S = {"padding": "10px 20px", "borderRadius": "8px 8px 0 0",
          "border": "none", "background": "transparent",
          "color": MUTED, "fontWeight": "600", "fontSize": "0.875rem"}
TAB_A = {**TAB_S, "color": TEXT, "background": CARD_BG,
         "borderBottom": f"2px solid {ACCENT}"}

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="Stock Sentiment Dashboard",
    suppress_callback_exceptions=True,
)


def make_layout():
    return html.Div([
        # Header
        html.Div([
            html.H1("Stock Sentiment Dashboard",
                    style={"fontSize": "1.8rem", "fontWeight": "900",
                           "margin": "0 0 4px", "color": TEXT,
                           "letterSpacing": "-0.02em"}),
            html.P("Real-time NLP sentiment from Yahoo Finance + Reddit  ·  "
                   "Powered by VADER  ·  Auto-refreshes every 5 minutes",
                   style={"margin": 0, "color": MUTED, "fontSize": "0.82rem"}),
        ], style={
            "background": "linear-gradient(135deg,rgba(124,58,237,0.22),"
                          "rgba(34,197,94,0.08))",
            "borderBottom": f"1px solid {BORDER}",
            "padding": "22px 32px",
        }),

        # Auto-refresh interval
        dcc.Interval(id="interval", interval=REFRESH_INTERVAL_S * 1000, n_intervals=0),

        # Tabs
        dcc.Tabs(id="tabs", value="feed", children=[
            dcc.Tab(label="📡  Live Feed",         value="feed",     style=TAB_S, selected_style=TAB_A),
            dcc.Tab(label="📈  Sentiment vs Price", value="chart",    style=TAB_S, selected_style=TAB_A),
            dcc.Tab(label="🎯  Earnings Watch",     value="earnings", style=TAB_S, selected_style=TAB_A),
            dcc.Tab(label="🏆  Leaderboard",        value="leader",   style=TAB_S, selected_style=TAB_A),
        ], style={"background": BG, "borderBottom": f"1px solid {BORDER}",
                  "padding": "0 32px"}),

        html.Div(id="tab-content", style={"padding": "24px 32px", "minHeight": "82vh"}),

        html.Div("Stock Sentiment Dashboard  ·  Yahoo Finance + Reddit  ·  VADER NLP",
                 style={"textAlign": "center", "color": MUTED, "fontSize": "0.72rem",
                        "padding": "14px", "borderTop": f"1px solid {BORDER}"}),
    ], style={"background": BG, "minHeight": "100vh",
              "fontFamily": "Inter, system-ui, sans-serif", "color": TEXT})


app.layout = make_layout


# ── Callbacks ──────────────────────────────────────────────────────────────────
@app.callback(Output("tab-content", "children"),
              Input("tabs", "value"))
def render_tab(tab):
    if tab == "feed":
        return html.Div([
            # Controls row
            html.Div([
                html.Div([
                    html.Label("Watchlist:", style={"color": MUTED, "fontSize": "0.78rem",
                                                    "marginBottom": "6px", "display": "block",
                                                    "textTransform": "uppercase"}),
                    ticker_dd("feed-tickers", DEFAULT_TICKERS[:8], multi=True),
                ], style={"flex": "1"}),
                html.Div([
                    html.Button("Refresh Now", id="refresh-btn",
                                style={"marginTop": "22px", "padding": "8px 20px",
                                       "background": ACCENT, "color": "white",
                                       "border": "none", "borderRadius": "8px",
                                       "cursor": "pointer", "fontWeight": "600",
                                       "fontSize": "0.85rem"}),
                ], style={"alignSelf": "flex-end", "marginLeft": "16px"}),
                html.Div(id="last-updated",
                         style={"alignSelf": "flex-end", "marginLeft": "16px",
                                "color": MUTED, "fontSize": "0.78rem"}),
            ], style={"display": "flex", "gap": "12px", "alignItems": "flex-start",
                      "marginBottom": "20px"}),

            # Stock cards row
            html.Div(id="stock-cards",
                     style={"display": "flex", "gap": "12px",
                            "flexWrap": "wrap", "marginBottom": "22px"}),

            # News table
            card([
                html.H3("Latest Headlines",
                        style={"margin": "0 0 14px", "fontSize": "1rem",
                               "fontWeight": "700", "color": TEXT}),
                html.Div(id="news-table"),
            ]),
        ])

    if tab == "chart":
        return html.Div([
            card([
                html.Div([
                    html.Div([
                        html.Label("Stock:", style={"color": MUTED, "fontSize": "0.78rem",
                                                    "marginBottom": "6px", "display": "block",
                                                    "textTransform": "uppercase"}),
                        ticker_dd("chart-ticker", "AAPL"),
                    ], style={"flex": "0 0 260px"}),
                    html.Div([
                        html.Label("History:", style={"color": MUTED, "fontSize": "0.78rem",
                                                      "marginBottom": "6px", "display": "block",
                                                      "textTransform": "uppercase"}),
                        dcc.RadioItems(
                            id="chart-days",
                            options=[{"label": l, "value": v} for l, v in
                                     [("7d", 7), ("14d", 14), ("30d", 30), ("60d", 60)]],
                            value=30, inline=True,
                            style={"color": TEXT, "gap": "16px"},
                            inputStyle={"marginRight": "5px"},
                        ),
                    ], style={"flex": "1", "marginLeft": "24px"}),
                ], style={"display": "flex", "alignItems": "flex-end",
                          "marginBottom": "16px"}),
                dcc.Graph(id="price-sentiment-chart",
                          config={"displayModeBar": False}),
            ]),
        ])

    if tab == "earnings":
        return html.Div([
            card([
                html.H3("Upcoming Earnings", style={"margin": "0 0 14px", "fontSize": "1rem",
                                                     "fontWeight": "700"}),
                html.Div(id="earnings-table"),
            ], {"marginBottom": "20px"}),
            card([
                html.Div([
                    html.Label("Pre-Earnings Sentiment:", style={"color": MUTED, "fontSize": "0.78rem",
                                                                  "marginBottom": "6px", "display": "block",
                                                                  "textTransform": "uppercase"}),
                    ticker_dd("earnings-ticker", "AMD"),
                ], style={"marginBottom": "12px"}),
                dcc.Graph(id="earnings-sentiment-chart", config={"displayModeBar": False},
                          figure=go.Figure(layout={**PL, "height": 280})),
            ]),
        ])

    if tab == "leader":
        return html.Div([
            html.Div(id="leader-kpis",
                     style={"display": "flex", "gap": "14px", "flexWrap": "wrap",
                            "marginBottom": "22px"}),
            html.Div([
                card([dcc.Graph(id="leaderboard-chart", config={"displayModeBar": False})],
                     {"flex": "1", "minWidth": "340px"}),
                card([
                    html.H3("Most Active", style={"fontSize": "0.9rem", "fontWeight": "700",
                                                   "marginBottom": "14px"}),
                    html.Div(id="most-active-list"),
                ], {"flex": "0 0 300px"}),
            ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap"}),
        ])


# Live Feed callbacks
@app.callback(
    [Output("stock-cards",   "children"),
     Output("news-table",    "children"),
     Output("last-updated",  "children")],
    [Input("interval",        "n_intervals"),
     Input("refresh-btn",     "n_clicks"),
     Input("feed-tickers",    "value")],
)
def update_feed(_, n_clicks, tickers):
    ctx = callback_context
    if ctx.triggered and "refresh-btn" in ctx.triggered[0]["prop_id"]:
        scheduler.force_refresh(tickers or DEFAULT_TICKERS)

    tickers  = tickers or DEFAULT_TICKERS[:8]
    quotes   = pricer.get_current_quotes(tickers)
    summary  = store.get_sentiment_summary()
    s_map    = ({r["ticker"]: r for _, r in summary.iterrows()}
                if not summary.empty else {})

    # Stock cards
    cards = [stock_card(t, quotes.get(t, {}), s_map.get(t)) for t in tickers]

    # News table
    df = store.get_headlines(days=1)
    if not df.empty:
        df = df[df["ticker"].isin(tickers)].head(100)

    if df.empty:
        table = html.P("Fetching headlines… check back in a moment.",
                       style={"color": MUTED, "padding": "20px 0"})
    else:
        rows = []
        for _, r in df.iterrows():
            ts   = str(r.get("fetched_at", ""))[:16].replace("T", " ")
            lbl  = str(r.get("label", "Neutral"))
            comp = float(r.get("compound", 0))
            rows.append(html.Tr([
                html.Td(ts, style={"color": MUTED, "whiteSpace": "nowrap",
                                   "fontSize": "0.75rem", "paddingRight": "12px"}),
                html.Td(html.Span(str(r.get("ticker", "")),
                                  style={"fontWeight": "700",
                                         "color": ACCENT}),
                        style={"paddingRight": "12px"}),
                html.Td(html.Span(str(r.get("source", "")),
                                  style={"color": MUTED, "fontSize": "0.73rem"}),
                        style={"paddingRight": "12px"}),
                html.Td(html.A(str(r.get("title", "")),
                               href=str(r.get("url", "#")),
                               target="_blank",
                               style={"color": TEXT, "textDecoration": "none",
                                      "fontSize": "0.85rem"}),
                        style={"paddingRight": "16px"}),
                html.Td(html.Div([
                    sentiment_badge(lbl),
                    html.Span(f"  {comp:+.3f}",
                              style={"color": sent.label_color(lbl),
                                     "fontSize": "0.72rem", "marginLeft": "4px"}),
                ])),
            ], style={"borderBottom": f"1px solid {BORDER}",
                      "verticalAlign": "middle"}))

        table = html.Table(
            [html.Thead(html.Tr([
                html.Th(h, style={"color": MUTED, "fontWeight": "600",
                                  "fontSize": "0.73rem", "textTransform": "uppercase",
                                  "padding": "0 12px 10px 0"})
                for h in ["Time", "Ticker", "Source", "Headline", "Sentiment"]
            ]))] + [html.Tbody(rows)],
            style={"width": "100%", "borderCollapse": "collapse"},
        )

    return cards, table, scheduler.last_run_str()


# Sentiment vs Price chart
@app.callback(
    Output("price-sentiment-chart", "figure"),
    [Input("chart-ticker", "value"),
     Input("chart-days",   "value"),
     Input("interval",     "n_intervals")],
)
def update_chart(ticker, days, _):
    return fig_sentiment_price(ticker or "AAPL", days or 30)


# Earnings — sentiment chart (fast: DB only)
@app.callback(
    Output("earnings-sentiment-chart", "figure"),
    [Input("earnings-ticker", "value"),
     Input("interval",        "n_intervals")],
)
def update_earnings_chart(ticker, _):
    return fig_earnings_sentiment(ticker or "AMD")


# Earnings — calendar table (slow: 15 network calls, runs independently)
@app.callback(
    Output("earnings-table", "children"),
    Input("interval", "n_intervals"),
)
def update_earnings_table(_):
    cal = pricer.get_earnings_calendar(DEFAULT_TICKERS)
    if not cal:
        return html.P("No upcoming earnings found for tracked tickers.",
                      style={"color": MUTED})
    rows = []
    for r in cal[:15]:
        d   = r["days_until"]
        col = GREEN if d <= 7 else (YELLOW if d <= 30 else MUTED)
        rows.append(html.Tr([
            html.Td(r["ticker"], style={"fontWeight": "700", "color": ACCENT}),
            html.Td(TICKER_NAMES.get(r["ticker"], ""), style={"color": MUTED}),
            html.Td(r["earnings_date"]),
            html.Td(html.Span(f"In {d} days" if d > 0 else "Today!",
                              style={"color": col, "fontWeight": "600"})),
        ], style={"borderBottom": f"1px solid {BORDER}"}))
    return html.Table(
        [html.Thead(html.Tr([
            html.Th(h, style={"color": MUTED, "fontWeight": "600",
                              "fontSize": "0.73rem", "textTransform": "uppercase",
                              "padding": "0 20px 10px 0"})
            for h in ["Ticker", "Company", "Date", "Countdown"]
        ]))] + [html.Tbody(rows)],
        style={"width": "100%", "borderCollapse": "collapse"},
    )


# Leaderboard callbacks
@app.callback(
    [Output("leaderboard-chart", "figure"),
     Output("leader-kpis",       "children"),
     Output("most-active-list",  "children")],
    Input("interval", "n_intervals"),
)
def update_leaderboard(_):
    summary = store.get_sentiment_summary()

    if summary.empty:
        empty_fig = go.Figure(layout={**PL, "title": {"text": "Fetching data…", "x": 0.5}})
        return empty_fig, [], []

    # KPI tiles
    avg_all  = float(summary["avg_compound"].mean())
    bullish  = int((summary["avg_compound"] >= 0.05).sum())
    bearish  = int((summary["avg_compound"] <= -0.05).sum())
    total_n  = int(summary["n_headlines"].sum())

    overall_label = "Bullish" if avg_all >= 0.05 else ("Bearish" if avg_all <= -0.05 else "Neutral")
    overall_color = GREEN if avg_all >= 0.05 else (RED if avg_all <= -0.05 else MUTED)

    kpis = [
        kpi("Market Sentiment",  overall_label, overall_color),
        kpi("Bullish Stocks",    str(bullish),  GREEN),
        kpi("Bearish Stocks",    str(bearish),  RED),
        kpi("Headlines (24h)",   f"{total_n:,}", ACCENT),
    ]

    # Most active list
    top = summary.nlargest(8, "n_headlines")
    active_items = []
    for _, r in top.iterrows():
        c     = float(r["avg_compound"])
        col   = GREEN if c >= 0.05 else (RED if c <= -0.05 else MUTED)
        active_items.append(html.Div([
            html.Span(r["ticker"], style={"fontWeight": "700", "color": ACCENT,
                                          "width": "48px", "display": "inline-block"}),
            html.Span(f"{int(r['n_headlines'])} articles",
                      style={"color": MUTED, "fontSize": "0.78rem",
                             "width": "90px", "display": "inline-block"}),
            html.Span(f"{c:+.3f}", style={"color": col, "fontWeight": "600",
                                           "fontSize": "0.85rem"}),
        ], style={"padding": "7px 0", "borderBottom": f"1px solid {BORDER}"}))

    return fig_leaderboard(summary), kpis, active_items


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\nStock Sentiment Dashboard")
    print("  -> http://localhost:8050\n")
    app.run(debug=False, port=8050, host="0.0.0.0")
