import streamlit as st
import requests
import re
from typing import List, Optional
import time

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
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("http")
    ]

def resolve_tiktok_url(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(
        url,
        headers=headers,
        allow_redirects=True,
        timeout=10
    )
    return response.url

def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r"/@[^/]+/video/(\d+)",
        r"/video/(\d+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

# ------------------ MOCK BACKEND ------------------
def mock_backend(video_id: str) -> dict:
    """
    This simulates a backend response.
    Replace this function later with a real API call.
    """
    time.sleep(0.5)  # simulate processing delay

    fake_video_bytes = b"FAKE MP4 DATA - REPLACE WITH REAL VIDEO STREAM"

    return {
        "title": f"TikTok Video {video_id}",
        "file_bytes": fake_video_bytes,
        "filename": f"{video_id}.mp4"
    }

# ------------------ MAIN ------------------
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

            st.success(f"{idx}. Video ready")
            st.write(f"**Video ID:** `{video_id}`")
            st.caption(resolved_url)

            # -------- CALL MOCK BACKEND --------
            backend_data = mock_backend(video_id)

            st.download_button(
                label=f"Download Video {idx}",
                data=backend_data["file_bytes"],
                file_name=backend_data["filename"],
                mime="video/mp4"
            )

        except requests.exceptions.RequestException:
            st.error(f"{idx}. Network error")
            st.caption(link)

        except Exception as e:
            st.error(f"{idx}. Unexpected error")
            st.caption(str(e))
