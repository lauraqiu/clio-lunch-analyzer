import streamlit as st
import pandas as pd
import plotly.express as px
import html
import json
import os
import requests
from lunch_analyzer import analyze_lunches
import sys
from io import StringIO
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import pytz

st.set_page_config(
    page_title="Slack Lunch Insights", 
    layout="wide", 
    initial_sidebar_state="expanded",
    menu_items=None
)

# Clio-inspired custom CSS
st.markdown("""
<style>
    /* Disable Streamlit dark mode */
    .stApp {
        background-color: #F5F7FA !important;
        color: #374151 !important;
    }
    
    /* Force light theme */
    [data-theme="dark"] {
        display: none !important;
    }
    
    /* Main background - light grey like Clio */
    .main {
        background-color: #F5F7FA !important;
        color: #374151 !important;
    }
    
    /* Sidebar styling - dark blue like Clio */
    [data-testid="stSidebar"] {
        background-color: #1E3A5F !important;
    }
    
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }
    
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: #FFFFFF !important;
    }
    
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span {
        color: #FFFFFF !important;
    }
    
    /* Main content area */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Headers - Clio blue */
    h1 {
        color: #1E3A5F;
        font-weight: 600;
        font-size: 2rem;
    }
    
    h2, h3 {
        color: #1E3A5F;
        font-weight: 600;
    }
    
    /* Buttons - Clio blue with white text */
    .stButton > button,
    button[kind="secondary"],
    button[kind="primary"],
    [data-testid="baseButton-secondary"],
    [data-testid="baseButton-primary"] {
        background-color: #0066CC !important;
        color: #FFFFFF !important;
        border-radius: 4px;
        border: none !important;
        font-weight: 500;
        padding: 0.5rem 1rem;
    }
    
    .stButton > button:hover,
    button[kind="secondary"]:hover,
    button[kind="primary"]:hover {
        background-color: #0052A3 !important;
        color: #FFFFFF !important;
    }
    
    /* Force all button text and children to be white */
    .stButton > button,
    .stButton > button *,
    .stButton > button span,
    .stButton > button p,
    .stButton > button div,
    button[kind="secondary"] *,
    button[kind="primary"] * {
        color: #FFFFFF !important;
    }
    
    /* Target button text specifically - all possible selectors */
    [data-testid="baseButton-secondary"] p,
    [data-testid="baseButton-primary"] p,
    [data-testid="baseButton-secondary"] span,
    [data-testid="baseButton-primary"] span,
    button p,
    button span,
    button div,
    .stButton button p,
    .stButton button span,
    .stButton button div {
        color: #FFFFFF !important;
    }
    
    /* Override any text color on buttons */
    button {
        color: #FFFFFF !important;
    }
    
    button * {
        color: #FFFFFF !important;
    }
    
    /* Metrics cards - white with subtle shadow */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 600;
        color: #1E3A5F;
    }
    
    [data-testid="stMetricLabel"] {
        color: #6B7280;
        font-size: 0.875rem;
    }
    
    [data-testid="stMetricDelta"] {
        font-size: 0.875rem;
    }
    
    /* Dividers */
    hr {
        border-color: #E5E7EB;
        margin: 2rem 0;
    }
    
    /* Select boxes and sliders */
    .stSelectbox label, .stSlider label, .stMultiSelect label {
        color: #374151;
        font-weight: 500;
    }
    
    /* Dataframe styling */
    .dataframe {
        background-color: white !important;
        border-radius: 4px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        color: #374151 !important;
    }
    
    .dataframe thead th {
        background-color: #F9FAFB !important;
        color: #1E3A5F !important;
        font-weight: 600;
        border-bottom: 2px solid #E5E7EB;
    }
    
    .dataframe tbody td {
        color: #374151 !important;
        background-color: white !important;
    }
    
    .dataframe tbody tr:hover {
        background-color: #F9FAFB !important;
    }
    
    .dataframe tbody tr:hover td {
        background-color: #F9FAFB !important;
    }
    
    /* Streamlit dataframe container */
    [data-testid="stDataFrame"] {
        background-color: white;
        border-radius: 4px;
        padding: 1rem;
    }
    
    /* Force table text colors */
    table {
        color: #374151 !important;
    }
    
    table td, table th {
        color: #374151 !important;
    }
    
    /* Override Streamlit's default table styling - force light mode */
    .stDataFrame, [data-testid="stDataFrame"] {
        background-color: white !important;
    }
    
    .stDataFrame table, [data-testid="stDataFrame"] table {
        background-color: white !important;
        color: #374151 !important;
    }
    
    .stDataFrame table td, [data-testid="stDataFrame"] table td {
        color: #374151 !important;
        background-color: white !important;
    }
    
    .stDataFrame table th, [data-testid="stDataFrame"] table th {
        color: #1E3A5F !important;
        background-color: #F9FAFB !important;
    }
    
    /* Override any dark mode table styling */
    [data-baseweb="table"] {
        background-color: white !important;
    }
    
    [data-baseweb="table"] td, [data-baseweb="table"] th {
        background-color: white !important;
        color: #374151 !important;
    }
    
    /* Force all table elements to light mode */
    table, thead, tbody, tr, td, th {
        background-color: white !important;
        color: #374151 !important;
    }
    
    table thead th {
        background-color: #F9FAFB !important;
        color: #1E3A5F !important;
    }
    
    /* Chart containers */
    [data-testid="stPlotlyChart"] {
        background-color: white;
        border-radius: 4px;
        padding: 1rem;
    }
    
    /* Subheaders */
    .subheader {
        color: #1E3A5F;
        font-weight: 600;
    }
    
    /* Text color - but not in sidebar - force dark text on light background */
    .main p, .main .stMarkdown, .main div, .main span {
        color: #374151 !important;
    }
    
    /* Ensure main content text is visible */
    .main {
        color: #374151 !important;
        background-color: #F5F7FA !important;
    }
    
    .main * {
        color: #374151 !important;
    }
    
    /* Exception: buttons should have white text */
    .main .stButton button,
    .main .stButton button *,
    .main button,
    .main button * {
        color: #FFFFFF !important;
    }
    
    /* Override for specific elements that should be dark */
    .main h1, .main h2, .main h3 {
        color: #1E3A5F !important;
    }
    
    /* Force all text in main area to be dark */
    .block-container p, .block-container div, .block-container span {
        color: #374151 !important;
    }
    
    /* Spinner */
    .stSpinner > div {
        border-top-color: #0066CC;
    }
    
    /* Force override any dark mode classes */
    [class*="dark"], [class*="Dark"] {
        background-color: #F5F7FA !important;
        color: #374151 !important;
    }
    
    /* Select and multiselect styling */
    [data-baseweb="select"], [data-baseweb="popover"] {
        background-color: white !important;
        color: #374151 !important;
    }
    
    /* Slider styling */
    [data-baseweb="slider"] {
        color: #0066CC !important;
    }
</style>
<script>
    // Force light mode
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'light');
    }
</script>
""", unsafe_allow_html=True)

# Header with refresh button and date range selector
col_title, col_range, col_refresh = st.columns([3, 1, 1])
with col_title:
    st.title("🍽️ Toronto Office Lunch Analytics")
    st.markdown("Insights and sentiment ratings from the #staff-toronto-the6ix channel.")
with col_range:
    st.markdown("<br>", unsafe_allow_html=True)  # Spacing
    days_back = st.selectbox(
        "Time Period",
        options=[30, 60, 90, 180, 365],
        format_func=lambda x: f"Last {x} days" if x < 365 else "Last year",
        index=0,
        key="days_selector"
    )
with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True)  # Spacing
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# 1. Fetch Data with automatic daily refresh at 2pm ET
@st.cache_data(ttl=3600, show_spinner=False)
def get_data(days_back, refresh_date_key):
    """
    Fetch lunch data. If LUNCH_DATA_URL is set (e.g. from a scheduled job),
    load from that URL; otherwise call Slack via analyze_lunches().
    """
    # Optional: load from a pre-built JSON URL (updated by GitHub Action or cron)
    data_url = None
    try:
        if hasattr(st, "secrets") and st.secrets:
            data_url = st.secrets.get("LUNCH_DATA_URL")
    except Exception:
        pass
    data_url = data_url or os.environ.get("LUNCH_DATA_URL")

    if data_url:
        try:
            r = requests.get(data_url, timeout=30)
            r.raise_for_status()
            data = r.json()
            if data and len(data) > 0:
                return data
        except Exception:
            pass  # Fall back to live fetch

    # Capture print output to avoid cluttering the UI
    f = StringIO()
    with redirect_stdout(f):
        results = analyze_lunches(days_back=days_back)
    return results

# Check current time in Eastern Timezone
et_tz = pytz.timezone('US/Eastern')
now_et = datetime.now(et_tz)

# Create a refresh key that changes daily after 2pm ET
# This ensures cache automatically refreshes after 2pm ET each day
if now_et.hour >= 14:  # After 2pm ET
    # Use today's date with "after-2pm" marker
    refresh_date_key = now_et.strftime('%Y-%m-%d-after-2pm')
else:
    # Before 2pm ET - use yesterday's date (so cache refreshes after 2pm)
    yesterday = (now_et - timedelta(days=1)).strftime('%Y-%m-%d')
    refresh_date_key = f"{yesterday}-before-2pm"

# Load data
with st.spinner(f"Fetching lunch data from Slack (past {days_back} days)..."):
    lunch_data = get_data(days_back, refresh_date_key)

if lunch_data is None or len(lunch_data) == 0:
    st.error("❌ No lunch data found. Please check your Slack credentials and channel ID.")
    st.stop()

# Convert to DataFrame
df = pd.DataFrame(lunch_data)
df['date'] = pd.to_datetime(df['date'])

# Ensure vendor and menu display & not &amp; (Slack HTML entities), and remove asterisks
def clean_display_text(x):
    if not isinstance(x, str):
        return x
    return html.unescape(x).replace('*', '').strip()
df['vendor'] = df['vendor'].apply(clean_display_text)
df['menu'] = df['menu'].apply(clean_display_text)

# Handle backward compatibility: rename old 'hype_score' to 'sentiment_rating' if it exists
if 'hype_score' in df.columns and 'sentiment_rating' not in df.columns:
    df['sentiment_rating'] = df['hype_score']
    df = df.drop(columns=['hype_score'])

# Metrics
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="Total Lunches Analyzed", value=len(df))

with col2:
    avg_score = df['sentiment_rating'].mean()
    st.metric(label="Average Sentiment Rating", value=f"{avg_score:.1f}")

with col3:
    top_score = df['sentiment_rating'].max()
    top_vendor = df.loc[df['sentiment_rating'].idxmax(), 'vendor']
    st.metric(label="Top Sentiment Rating", value=f"{top_score:.0f}", delta=top_vendor)

st.divider()

# Charts
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 Sentiment Rating Over Time")
    chart_data = df.sort_values('date')
    fig = px.line(chart_data, x='date', y='sentiment_rating', markers=True,
                  title="Sentiment Rating Trend",
                  labels={'sentiment_rating': 'Sentiment Rating', 'date': 'Date'})
    fig.update_traces(line_color='#0066CC', marker_color='#0066CC', line_width=2)
    fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', font_color='#374151')
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("🏆 Top Vendors by Highest Sentiment")
    # Get the highest sentiment rating for each vendor
    vendor_scores = df.groupby('vendor')['sentiment_rating'].max().sort_values(ascending=False)
    
    # Show top 20 vendors (or all if less than 20)
    top_vendors = vendor_scores.head(20)
    
    # Create the chart with top vendors (highest at top)
    fig = px.bar(x=top_vendors.values, y=top_vendors.index, orientation='h',
                 title=f"Highest Sentiment Rating by Vendor (Top {len(top_vendors)})",
                 labels={'x': 'Highest Sentiment Rating', 'y': 'Vendor'})
    fig.update_traces(marker_color='#0066CC')
    fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', font_color='#374151', yaxis={'autorange': 'reversed'})
    st.plotly_chart(fig, use_container_width=True)
    
    # Debug: Show if Sarang Kitchen is in the data
    if 'Sarang' in df['vendor'].values or 'sarang' in df['vendor'].str.lower().values:
        sarang_data = df[df['vendor'].str.contains('Sarang', case=False, na=False)]
        if len(sarang_data) > 0:
            st.caption(f"ℹ️ Sarang Kitchen found: {len(sarang_data)} lunch(es), max rating: {sarang_data['sentiment_rating'].max()}")

st.divider()

# Data table
st.subheader("📋 Ranked Lunch History")

# Add filters
col1, col2 = st.columns(2)
with col1:
    selected_vendors = st.multiselect("Filter by Vendor", options=sorted(df['vendor'].unique()), default=[])
with col2:
    min_score = st.slider("Minimum Sentiment Rating", min_value=0, max_value=int(df['sentiment_rating'].max()), value=0)

# Filter data
filtered_df = df.copy()
if selected_vendors:
    filtered_df = filtered_df[filtered_df['vendor'].isin(selected_vendors)]
filtered_df = filtered_df[filtered_df['sentiment_rating'] >= min_score]

# Display table
display_df = filtered_df[['rank', 'date', 'weekday', 'vendor', 'sentiment_rating', 'reply_count', 'menu']].copy()
display_df.columns = ['Rank', 'Date', 'Day', 'Vendor', 'Sentiment Rating', 'Replies', 'Menu']
display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m-%d')

st.dataframe(display_df, use_container_width=True, hide_index=True)