import streamlit as st
from PIL import Image, ImageFile
import io

# ================= SAFETY =================
ImageFile.LOAD_TRUNCATED_IMAGES = True
# =========================================

# ================= CONFIGURATION =================
# A4 at ~200 DPI (much safer for RAM, still sharp)
A4_WIDTH = 1654
A4_HEIGHT = 2339
# =================================================

def split_and_merge_images(uploaded_files):
    """Split long images and stitch them into A4 pages (memory-safe)."""

    sorted_files = sorted(uploaded_files, key=lambda x: x.name)

    if not sorted_files:
        return None

    st.info(f"Found {len(sorted_files)} images. Starting conversion...")

    output_pages = []
    current_file_index = 0
    current_img = None
    current_y_cursor = 0
    finished = False

    # Load first image safely
    with Image.open(sorted_files[current_file_index]) as img:
        img = img.convert("RGB")
        ratio = A4_WIDTH / float(img.width)
        new_height = int(img.height * ratio)
        current_img = img.resize(
            (A4_WIDTH, new_height),
            Image.Resampling.BILINEAR
        )

    while not finished:
        new_page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")
        current_page_y = 0

        while current_page_y < A4_HEIGHT:
            space_left_on_page = A4_HEIGHT - current_page_y
            img_data_left = current_img.height - current_y_cursor

            if img_data_left <= 0:
                current_file_index += 1
                if current_file_index >= len(sorted_files):
                    finished = True
                    break

                with Image.open(sorted_files[current_file_index]) as img:
                    img = img.convert("RGB")
                    ratio = A4_WIDTH / float(img.width)
                    new_height = int(img.height * ratio)
                    current_img = img.resize(
                        (A4_WIDTH, new_height),
                        Image.Resampling.BILINEAR
                    )

                current_y_cursor = 0
                img_data_left = current_img.height

            cut_height = min(space_left_on_page, img_data_left)

            box = (0, current_y_cursor, A4_WIDTH, current_y_cursor + cut_height)
            slice_img = current_img.crop(box)

            new_page.paste(slice_img, (0, current_page_y))

            # 🔴 CRITICAL: free memory
            slice_img.close()
            del slice_img

            current_page_y += cut_height
            current_y_cursor += cut_height

        if current_page_y > 0:
            output_pages.append(new_page)

    if not output_pages:
        return None

    pdf_buffer = io.BytesIO()
    output_pages[0].save(
        pdf_buffer,
        "PDF",
        resolution=72.0,
        save_all=True,
        append_images=output_pages[1:]
    )
    pdf_buffer.seek(0)

    return pdf_buffer

# ================= STREAMLIT APP =================

st.title("📄 A4 Long Image PDF Splitter")
st.markdown(
    "Upload long images (manhwa, comics, infographics). "
    "They will be split and merged into continuous A4 pages."
)

uploaded_files = st.file_uploader(
    "Upload JPG or PNG images (file name order is preserved)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Generate A4 PDF"):
        with st.spinner("Processing images and building PDF..."):
            pdf_data = split_and_merge_images(uploaded_files)

            if pdf_data:
                size_mb = len(pdf_data.getvalue()) / (1024 * 1024)
                st.success(f"PDF generated successfully ({size_mb:.2f} MB)")
                st.download_button(
                    label="Download Final_Output.pdf",
                    data=pdf_data,
                    file_name="Final_Output.pdf",
                    mime="application/pdf"
                )
            else:
                st.error("Processing failed. Please check your images.")

#python -m streamlit run app.py