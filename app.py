import streamlit as st
import requests
import re
from typing import List, Optional

# ------------------ PAGE CONFIG ------------------
st.set_page_config(
    page_title="TikTok Video Downloader",
    layout="centered"
)

st.title("TikTok Video Downloader")
st.caption("Download public TikTok videos. One click per video.")

# ------------------ INPUT ------------------
links_text = st.text_area(
    "Paste TikTok links (one per line)",
    height=200,
    placeholder=(
        "https://vt.tiktok.com/...\n"
        "https://www.tiktok.com/@username/video/1234567890"
    )
)

process_btn = st.button("Process Links")

# ------------------ HELPERS ------------------
def normalize_links(text: str) -> List[str]:
    """Extract valid-looking URLs from input"""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("http")
    ]

def resolve_tiktok_url(url: str) -> str:
    """Resolve short TikTok URLs (vt.tiktok.com, t.tiktok.com)"""
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

# ------------------ MAIN LOGIC ------------------
if process_btn:
    links = normalize_links(links_text)

    if not links:
        st.warning("No valid TikTok links found.")
        st.stop()

    st.info(f"Processing {len(links)} links...")

    for idx, link in enumerate(links, start=1):
        st.divider()

        try:
            resolved_url = resolve_tiktok_url(link)
            video_id = extract_video_id(resolved_url)

            if not video_id:
                st.error(f"{idx}. Could not extract video ID")
                st.caption(resolved_url)
                continue

            st.success(f"{idx}. Video ID extracted")
            st.write(f"**Video ID:** `{video_id}`")
            st.caption(resolved_url)

            # ------------------------------
            # PLACEHOLDER FOR BACKEND CALL
            # ------------------------------
            # Example expected backend response:
            # {
            #   "title": "Video title",
            #   "download_url": "https://cdn.example.com/video.mp4",
            #   "filename": "video.mp4"
            # }

            st.warning("Download not available yet (backend not connected)")

        except requests.exceptions.RequestException:
            st.error(f"{idx}. Network error while resolving link")
            st.caption(link)

        except Exception as e:
            st.error(f"{idx}. Unexpected error")
            st.caption(str(e))
