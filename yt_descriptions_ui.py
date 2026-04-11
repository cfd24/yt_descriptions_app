import streamlit as st
import subprocess
import sys
import os
import tempfile
import pandas as pd
import datetime
import hmac
import gspread
from oauth2client.service_account import ServiceAccountCredentials

@st.cache_data(ttl=3600)
def load_sheet_data(sheet_name="YT_Scraper_DB"):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = None
    
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    elif os.path.exists("google_credentials.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_credentials.json", scope)
    else:
        raise ValueError("No Google Credentials found.")
        
    client = gspread.authorize(creds)
    sheet = client.open(sheet_name).sheet1
    data = sheet.get_all_values()
    if not data: return pd.DataFrame()
    return pd.DataFrame(data[1:], columns=data[0])

# Install playwright automatically (mainly for Cloud deployment)
os.system("playwright install chromium > /dev/null 2>&1")

def check_password():
    """Returns `True` if the user had the correct password."""
    if "app_password" not in st.secrets:
        return True
        
    def password_entered():
        if hmac.compare_digest(st.session_state["password"], st.secrets["app_password"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 Restricted Access")
    st.text_input("Please enter the password to access this tool:", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state:
        st.error("😕 Password incorrect")
    return False

if not check_password():
    st.stop()

# Path to the scripts
DISCOVER_SCRIPT = os.path.join(os.path.dirname(__file__), 'youtube_api_discovery', 'discover_channels_api.py')
EXTRACT_SCRIPT = os.path.join(os.path.dirname(__file__), 'channels_to_description.py')

st.title("📺 YouTube Channel Discovery Tools")
st.markdown("Discover new channels and easily extract their about-page descriptions and contact emails.")

# Default API key from Streamlit secrets (so it doesn't leak to GitHub)
try:
    DEFAULT_API_KEY = st.secrets.get("api_keys", "")
except FileNotFoundError:
    DEFAULT_API_KEY = ""

with st.expander("⚙️ API Settings & Authentication"):
    st.markdown("Enter your YouTube Data v3 API key. Must be a single valid key to comply with Google Cloud TOS.")
    api_key_str = st.text_input("API Key", value=DEFAULT_API_KEY, type="password")

tab1, tab2, tab3 = st.tabs(["🔍 Discover Channels", "📝 Extract Descriptions", "📊 Database Explorer"])

with tab1:
    st.header("🔍 Discover New YouTube Channels")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        query = st.text_input("Search Query", value="", help="Leave blank to use default game-related queries")
        existing_csv = st.file_uploader("Existing Channels CSV (optional, to skip duplicates)", type=['csv'])
        
    with col2:
        max_new_channels = st.number_input("Max New Channels", min_value=1, max_value=10000, value=100, step=50)
        include_recent_date = st.checkbox("Include recent video date", help="Costs ~100 units/channel")
        include_avg_views = st.checkbox("Include avg views last month", help="Costs ~200-500 units/channel")
        
    col_out1, col_out2 = st.columns(2)
    with col_out1:
        default_filename = f"outputs/yt_discover_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output_path = st.text_input("Output CSV Path", value=default_filename)
        
    with col_out2:
        google_sheet = st.text_input("Append to Google Sheet (Title)", value="YT_Scraper_DB", help="Leave blank to save to local CSV only.")
    
    # Estimate costs
    num_queries = 11 if not query else 1  # Default queries count
    search_requests_per_query = (max_new_channels + 49) // 50  # Ceil division for requests needed
    base_cost = search_requests_per_query * 100 * num_queries  # Search costs
    channel_cost = max_new_channels * 1  # Channels list
    extra_cost = 0
    if include_recent_date:
        extra_cost += max_new_channels * 100
    if include_avg_views:
        extra_cost += max_new_channels * 300
    total_cost = base_cost + channel_cost + extra_cost
    
    # Calculate dynamic quota limit based on single key
    total_quota = 10000
    
    st.metric(label="Estimated API Cost (Units)", value=f"{total_cost:,}", 
              delta=f"Quota Left: {total_quota - total_cost:,} (approx)" if total_cost <= total_quota else f"Exceeds {total_quota:,}/day limit!", 
              delta_color="normal" if total_cost <= total_quota else "inverse")
    
    if st.button("Discover Channels"):
        with st.spinner("Discovering..."):
            cmd = [sys.executable, DISCOVER_SCRIPT, '--max-channels', str(max_new_channels), '--output', output_path, '--api-key', api_key_str]
            if query:
                cmd.extend(['--query', query])
            if include_recent_date:
                cmd.append('--include-recent-date')
            if include_avg_views:
                cmd.append('--include-avg-views')
            
            if google_sheet.strip():
                cmd.extend(['--google-sheet', google_sheet.strip()])
                
            if existing_csv:
                # Save uploaded file to temp
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_existing:
                    tmp_existing.write(existing_csv.getvalue())
                    existing_path = tmp_existing.name
                cmd.extend(['--existing-csv', existing_path])
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(__file__))
            
            if result.returncode == 0:
                if google_sheet.strip():
                    st.success(f"Discovery completed! Appended new channels to Google Sheet: {google_sheet}")
                    # Parse the standard output to show log
                    if result.stdout:
                        st.text_area("Log Output", result.stdout, height=150)
                else:
                    st.success("Discovery completed!")
                    st.text("Output: " + output_path)
                    try:
                        df = pd.read_csv(output_path)
                        st.dataframe(df.head())
                        
                        with open(output_path, 'rb') as f:
                            st.download_button(
                                label="Download CSV",
                                data=f,
                                file_name=os.path.basename(output_path),
                                mime="text/csv"
                            )
                    except Exception:
                        st.error("Failed to load output CSV")
            else:
                st.error("Error during discovery:")
                st.text_area("Error Output", result.stderr, height=300)
                if result.stdout:
                    st.text_area("Standard Output", result.stdout, height=300)

with tab2:
    st.header("Extract Channel Descriptions")
    
    st.markdown("Upload a CSV with columns: video_url, video_title, channel_url, channel_name.")
    
    uploaded_file = st.file_uploader("Upload input CSV", type=['csv'])
    
    if uploaded_file is not None:
        # Display preview
        df = pd.read_csv(uploaded_file)
        st.write("Preview of uploaded CSV:")
        st.dataframe(df.head())
        
        if st.button("Extract Descriptions"):
            with st.spinner("Processing... This may take a while."):
                # Save uploaded file to temp
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_in:
                    tmp_in.write(uploaded_file.getvalue())
                    input_path = tmp_in.name
                
                # Output path
                default_out_2 = f"channels_with_descriptions_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                output_path = os.path.join('outputs', default_out_2)
                
                # Run the script
                cmd = [sys.executable, EXTRACT_SCRIPT, '--input', input_path, '--output', output_path]
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(__file__))
                
                if result.returncode == 0:
                    st.success("Extraction completed!")
                    # Load and display output
                    output_df = pd.read_csv(output_path)
                    st.write("Output CSV preview:")
                    st.dataframe(output_df.head())
                    
                    # Download button
                    with open(output_path, 'rb') as f:
                        st.download_button(
                            label="Download Output CSV",
                            data=f,
                            file_name="channels_with_descriptions.csv",
                            mime="text/csv"
                        )
                else:
                    st.error("Error during extraction:")
                    st.text_area("Error Output", result.stderr, height=300)
                    if result.stdout:
                        st.text_area("Standard Output", result.stdout, height=300)

with tab3:
    st.header("📊 Database Explorer")
    st.markdown("Live view of your Google Spreadsheet with advanced filtering and relevance scoring.")
    
    sheet_name = st.text_input("Google Sheet Name", value="YT_Scraper_DB", key="db_sheet_name")
    
    if st.button("Load Database / Refresh"):
        try:
            with st.spinner("Fetching live data from Google Sheets..."):
                df = load_sheet_data(sheet_name)
            
            if df.empty:
                st.warning("Spreadsheet is empty.")
            else:
                st.success(f"Loaded {len(df)} channels successfully!")
                st.session_state['db_df'] = df
        except Exception as e:
            st.error(f"Error loading database: {str(e)}")
            
    if 'db_df' in st.session_state:
        df = st.session_state['db_df'].copy()
        
        # Convert subscribers to numeric
        def clean_number(x):
            if pd.isna(x) or x == 'N/A' or not str(x).strip(): return 0
            x = str(x).strip().upper()
            if 'M' in x: return float(x.replace('M', '')) * 1000000
            elif 'K' in x: return float(x.replace('K', '')) * 1000
            try: return float(x)
            except: return 0
            
        df['subscribers_num'] = df['subscribers'].apply(clean_number)
        
        # Relevance Score (Overlap)
        df['Relevance Score'] = df['queries'].apply(lambda x: len(str(x).split(';')) if pd.notna(x) and str(x).strip() else 0)
        
        # Interactive Filters
        st.subheader("Filter & Sort")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if 'description_language' in df.columns:
                languages = sorted([lang for lang in df['description_language'].unique() if pd.notna(lang) and lang.strip() != ''])
                if 'en' in languages:
                    languages.remove('en')
                    languages.insert(0, 'en')
                selected_langs = st.multiselect("Language Filter", options=languages)
            else:
                selected_langs = []
        with col2:
            min_subs = st.number_input("Minimum Subscribers", value=0, min_value=0, step=1000)
        with col3:
            query_search = st.text_input("Filter by Query/Niche", value="")
        with col4:
            st.write("") # Adjust vertical alignment with text inputs
            st.write("")
            require_emails = st.checkbox("Has Emails Only")
            
        # Apply Filters
        filtered_df = df[df['subscribers_num'] >= min_subs]
        if selected_langs and 'description_language' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['description_language'].isin(selected_langs)]
        if query_search:
            filtered_df = filtered_df[filtered_df['queries'].str.contains(query_search, case=False, na=False)]
        if require_emails and 'emails' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['emails'].notna() & (filtered_df['emails'].str.strip() != '')]
            
        st.markdown(f"**Showing {len(filtered_df):,} / {len(df):,} channels**")
        
        # Sort by relevance and then subs
        filtered_df = filtered_df.sort_values(by=['Relevance Score', 'subscribers_num'], ascending=[False, False])
        
        # Display Table
        display_cols = ['channel_name', 'channel_url', 'subscribers', 'Relevance Score', 'emails', 'description_language', 'queries']
        display_cols = [c for c in display_cols if c in filtered_df.columns]
        
        st.dataframe(
            filtered_df[display_cols],
            column_config={
                "channel_url": st.column_config.LinkColumn("Channel URL"),
                "Relevance Score": st.column_config.NumberColumn("Relevance", format="%d overlaps"),
                "emails": st.column_config.TextColumn("Emails")
            },
            hide_index=True,
            use_container_width=True
        )