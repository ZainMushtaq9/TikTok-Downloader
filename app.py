import streamlit as st
import requests
from typing import List

st.set_page_config(
    page_title="TikTok Downloader",
    layout="centered"
)

st.title("TikTok Video Downloader")
st.caption("Download public TikTok videos. One click per video.")

# --- INPUT ---
links_text = st.text_area(
    "Paste TikTok links (one per line)",
    height=180,
    placeholder="https://www.tiktok.com/...\nhttps://vm.tiktok.com/..."
)

download_format = st.selectbox(
    "Format",
    ["MP4 (video)", "MP3 (audio)"]
)

process_btn = st.button("Process Links")

# --- HELPERS ---
def normalize_links(text: str) -> List[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("http")
    ]

def fetch_video_metadata(tiktok_url: str) -> dict:
    """
    Placeholder:
    Call your backend service here.
    This function must return:
    {
        "title": "...",
        "download_url": "...",
        "filename": "video.mp4"
    }
    """
    raise NotImplementedError

# --- MAIN ---
if process_btn:
    links = normalize_links(links_text)

    if not links:
        st.warning("No valid links found.")
        st.stop()

    st.info(f"Processing {len(links)} links...")

    for idx, link in enumerate(links, start=1):
        with st.spinner(f"Fetching video {idx}"):
            try:
                data = fetch_video_metadata(link)

                st.success(data["title"])

                file_bytes = requests.get(data["download_url"]).content

                st.download_button(
                    label=f"Download {idx}",
                    data=file_bytes,
                    file_name=data["filename"],
                    mime="video/mp4" if "MP4" in download_format else "audio/mpeg"
                )

            except Exception as e:
                st.error(f"Failed: {link}")
