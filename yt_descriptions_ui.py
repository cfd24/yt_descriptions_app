import streamlit as st
import subprocess
import sys
import os
import tempfile
import pandas as pd
import datetime
import hmac

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

tab1, tab2 = st.tabs(["🔍 Discover Channels", "📝 Extract Descriptions"])

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