import streamlit as st
import requests
import re
from typing import List, Optional

st.set_page_config(page_title="TikTok Video Downloader", layout="centered")

st.title("TikTok Video Downloader")
st.caption("Download public TikTok videos. One click per video.")

# ---------- INPUT ----------
links_text = st.text_area(
    "Paste TikTok links (one per line)",
    height=180,
    placeholder="https://vt.tiktok.com/...\nhttps://www.tiktok.com/@user/video/..."
)

process_btn = st.button("Process Links")

# ---------- HELPERS ----------
def normalize_links(text: str) -> List[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("http")
    ]

def resolve_tiktok_url(url: str) -> str:
    """Resolve short TikTok URLs to canonical form"""
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(
        url,
        headers=headers,
        allow_redirects=True,
        timeout=10
    )
    return response.url

def extract_video_id(url: str) -> Optional[str]:
    """
    Supports:
    - https://www.tiktok.com/@username/video/1234567890
    - https://www.tiktok.com/video/1234567890
    """
    patterns = [
        r"/@[^/]+/video/(\d+)",
        r"/video/(\d+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None

# ---------- MAIN ----------
if process_btn:
    links = normalize_links(links_text)

    if not links:
        st.warning("No valid links found.")
        st.stop()

    st.info(f"Processing {len(links)} links...")

    for idx, link in enumerate(links, start=1):
        try:
            resolved_url = resolve_tiktok_url(link)
            video_id = extract_video_id(resolved_url)

            if not video_id:
                st.error(f"{idx}. Could not extract video ID")
                st.caption(resolved_url)
                continue

            st.success(f"{idx}. Video ID extracted")
            st.code(video_id)
            st.caption(resolved_url)

            # NEXT STEP:
            # Send `video_id` or `resolved_url` to your backend
            # which returns a downloadable media URL

        except Exception as e:
            st.error(f"{idx}. Failed to process link")
            st.caption(link)
