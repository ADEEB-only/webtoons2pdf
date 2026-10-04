import io
import re

import streamlit as st
from PIL import Image, ImageFile, ImageOps

# ================= SAFETY =================
ImageFile.LOAD_TRUNCATED_IMAGES = True
# Super-long webtoon strips can exceed Pillow's default decompression-bomb
# threshold (~178M pixels) which raises DecompressionBombError and crashes
# the app. Raise it to a generous but sane cap.
Image.MAX_IMAGE_PIXELS = 500_000_000
# =========================================

# ================= CONFIGURATION =================
# A4 at ~200 DPI (sharp for reading, safe for RAM)
A4_WIDTH = 1654
A4_HEIGHT = 2339
PDF_DPI = 200.0  # 1654px / 200dpi = 8.27in -> exactly A4 width in the PDF
# =================================================


def natural_key(name: str):
    """Natural sort key so img2.png comes before img10.png."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def split_and_merge_images(uploaded_files, progress_callback=None):
    """
    Split long images and stitch them into continuous A4 pages (memory-safe).

    progress_callback(done: int, total: int) is invoked per processed file.
    Returns a BytesIO containing the PDF, or None.
    """
    sorted_files = sorted(uploaded_files, key=lambda f: natural_key(f.name))
    if not sorted_files:
        return None

    output_pages = []
    n_files = len(sorted_files)
    img = None       # currently open source image (RGB, EXIF-corrected)
    src_y = 0        # source rows already consumed from the current image
    state = {"idx": 0}

    def load_next():
        nonlocal img, src_y
        while state["idx"] < n_files:
            f = sorted_files[state["idx"]]
            state["idx"] += 1
            try:
                # UploadedFile buffers persist across Streamlit reruns and
                # PIL reads them lazily, so after the first run the pointer
                # sits at EOF -> "cannot identify image file" crash on rerun.
                f.seek(0)
                with Image.open(f) as im:
                    im = ImageOps.exif_transpose(im)  # respect phone rotation
                    im.load()                          # read fully, then close
                    if im.width == 0 or im.height == 0:
                        continue
                    img = im.convert("RGB")
                    src_y = 0
                    if progress_callback:
                        progress_callback(state["idx"], n_files)
                    return True
            except Exception:
                # Skip corrupt/unreadable files instead of crashing the run
                continue
        return False

    if not load_next():
        return None

    while img is not None:
        page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")
        page_y = 0

        while page_y < A4_HEIGHT:
            src_left = img.height - src_y
            if src_left <= 0:
                img.close()
                img = None
                if not load_next():
                    break
                continue

            # Slice from the ORIGINAL image (never a giant pre-resized
            # strip) and resize only the slice -> constant memory usage.
            scale = A4_WIDTH / img.width
            room_px = A4_HEIGHT - page_y
            cut_src = min(int(room_px / scale), src_left)
            # If rounding left a sliver of page space (< 1 source row),
            # consume 1 source row so no white seam line appears at the cut.
            if cut_src == 0 and src_left > 0:
                cut_src = 1
            pasted_h = min(max(1, round(cut_src * scale)), room_px)

            slice_img = img.crop((0, src_y, img.width, src_y + cut_src))
            slice_img = slice_img.resize(
                (A4_WIDTH, pasted_h), Image.Resampling.BILINEAR
            )
            page.paste(slice_img, (0, page_y))
            slice_img.close()

            page_y += pasted_h
            src_y += cut_src

        if page_y > 0:
            output_pages.append(page)
        else:
            page.close()

    if not output_pages:
        return None

    pdf_buffer = io.BytesIO()
    # resolution=PDF_DPI maps the pixel grid exactly onto A4 paper.
    # (The old resolution=72.0 produced a ~23 x 32 inch page, not A4.)
    output_pages[0].save(
        pdf_buffer,
        "PDF",
        resolution=PDF_DPI,
        save_all=True,
        append_images=output_pages[1:],
    )
    for p in output_pages:
        p.close()
    pdf_buffer.seek(0)
    return pdf_buffer


# ================= STREAMLIT APP =================

st.set_page_config(page_title="WebToons to A4 PDF", page_icon="📄")
st.title("📄 WebToons to A4 page PDF maker")
st.markdown(
    "Upload long images (manhwa, comics, infographics). "
    "They will be split and merged into continuous A4 pages."
)

uploaded_files = st.file_uploader(
    "Upload JPG or PNG images (naturally sorted by file name)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.caption(f"{len(uploaded_files)} file(s) ready.")
    if st.button("Generate A4 PDF", type="primary"):
        progress_bar = st.progress(0, text="Processing images...")
        with st.spinner("Processing images and building PDF..."):
            pdf_data = split_and_merge_images(
                uploaded_files,
                progress_callback=lambda done, total: progress_bar.progress(
                    done / total, text=f"Processing image {done}/{total}..."
                ),
            )

        progress_bar.empty()
        if pdf_data:
            size_mb = len(pdf_data.getvalue()) / (1024 * 1024)
            st.success(f"PDF generated successfully ({size_mb:.2f} MB)")
            st.download_button(
                label="Download Final_Output.pdf",
                data=pdf_data,
                file_name="Final_Output.pdf",
                mime="application/pdf",
            )
        else:
            st.error("No readable images found. Please check your files.")
