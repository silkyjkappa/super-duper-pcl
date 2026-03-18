import streamlit as st
import os
from pathlib import Path
from PIL import Image
import re
import pandas as pd
import base64
import io
import hashlib
import difflib

# === CONFIG ===
PARENT_DIR = Path(__file__).parent


# === SESSION STATE INITIALIZATION ===
def init_session_state():
    """Initialize session state variables"""
    defaults = {
        'recent_searches': [],
        'favorites': [],
        'selected_position': None,
        'selected_stack': None,
        'selected_action': None,
        'images_loaded': False,
        'search_query': '',
        'show_results': False
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# === ENHANCED FUNCTIONS ===
@st.cache_data
def load_images(directory_path):
    """Load and parse poker chart images with metadata"""
    directory = Path(directory_path)
    if not directory.exists():
        return [], pd.DataFrame()

    hero_positions = ['BB', 'SB', 'BTN']
    stack_pattern = r'\d+bb'
    action_pattern = r'(\d+(?:\.\d+)?r|[cfr]|shove|bet|3bet)'

    images = []
    metadata = {
        'file_path': [], 'hero_position': [], 'stack_size': [],
        'actions': [], 'hu': [], 'filename': []
    }

    for file_path in directory.rglob("*.png"):
        filename = file_path.name
        parts = filename.replace('.png', '').split()

        hero_pos = None
        stack_size = None
        actions = []
        hu = False

        if parts and parts[0] in hero_positions:
            hero_pos = parts[0]
            if len(parts) > 1 and re.match(stack_pattern, parts[1]):
                stack_size = parts[1]
                remaining = parts[2:]
                if remaining and remaining[0].upper() == 'HU':
                    hu = True
                    remaining = remaining[1:]
                for i in range(0, len(remaining), 2):
                    if i + 1 < len(remaining) and remaining[i] in hero_positions and re.match(action_pattern,
                                                                                              remaining[i + 1]):
                        actions.append(f"{remaining[i]} {remaining[i + 1]}")

        if hero_pos and stack_size:
            images.append(file_path)
            metadata['file_path'].append(str(file_path))
            metadata['hero_position'].append(hero_pos)
            metadata['stack_size'].append(stack_size)
            metadata['actions'].append(' '.join(actions) if actions else 'None')
            metadata['hu'].append(hu)
            metadata['filename'].append(filename)

    return images, pd.DataFrame(metadata)


@st.cache_data
def image_to_base64(image_path, crop_bottom=True):
    """Convert image to base64 string with optional cropping"""
    try:
        image = Image.open(image_path)

        if crop_bottom:
            # Crop bottom 25% of the image to remove non-pertinent information
            width, height = image.size
            crop_height = int(height * 0.75)  # Keep top 75% of the image
            image = image.crop((0, 0, width, crop_height))

        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception as e:
        st.error(f"Error converting image {image_path}: {e}")
        return None


def create_large_image_html(image_path, caption=""):
    """Create a responsive image with native fullscreen support showing original uncropped image"""
    # Get cropped version for display
    cropped_img_b64 = image_to_base64(image_path, crop_bottom=True)
    # Get full original image for fullscreen
    full_img_b64 = image_to_base64(image_path, crop_bottom=False)

    if not cropped_img_b64 or not full_img_b64:
        return None

    # Generate unique IDs for this image
    import hashlib
    unique_id = hashlib.md5(str(image_path).encode()).hexdigest()[:8]

    html_code = f"""
    <div style="margin-bottom: 8px; text-align: center;">
        <img id="display-img-{unique_id}" 
             src="data:image/png;base64,{cropped_img_b64}" 
             class="large-chart-image"
             alt="{caption}"
             onclick="showFullscreen{unique_id}()"
             style="cursor: pointer; width: 100%; max-height: 400px; object-fit: contain; display: block; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);"
             title="Click to view fullscreen">

        <!-- Hidden full-size image for fullscreen -->
        <img id="fullscreen-img-{unique_id}" 
             src="data:image/png;base64,{full_img_b64}" 
             style="display: none; width: 100%; height: 100%; object-fit: contain; background-color: black;"
             alt="{caption}">
    </div>

    <script>
        function showFullscreen{unique_id}() {{
            const fullscreenImg = document.getElementById('fullscreen-img-{unique_id}');
            const displayImg = document.getElementById('display-img-{unique_id}');

            // Switch to full image and request fullscreen
            displayImg.style.display = 'none';
            fullscreenImg.style.display = 'block';

            // Request fullscreen on the full image
            if (fullscreenImg.requestFullscreen) {{
                fullscreenImg.requestFullscreen().catch(e => console.log('Fullscreen not supported:', e));
            }} else if (fullscreenImg.webkitRequestFullscreen) {{
                fullscreenImg.webkitRequestFullscreen();
            }} else if (fullscreenImg.msRequestFullscreen) {{
                fullscreenImg.msRequestFullscreen();
            }}
        }}

        // Listen for fullscreen exit to restore display
        document.addEventListener('fullscreenchange', function() {{
            if (!document.fullscreenElement) {{
                const displayImg = document.getElementById('display-img-{unique_id}');
                const fullscreenImg = document.getElementById('fullscreen-img-{unique_id}');

                if (displayImg && fullscreenImg) {{
                    displayImg.style.display = 'block';
                    fullscreenImg.style.display = 'none';
                }}
            }}
        }});

        // Handle webkit fullscreen change (Safari)
        document.addEventListener('webkitfullscreenchange', function() {{
            if (!document.webkitFullscreenElement) {{
                const displayImg = document.getElementById('display-img-{unique_id}');
                const fullscreenImg = document.getElementById('fullscreen-img-{unique_id}');

                if (displayImg && fullscreenImg) {{
                    displayImg.style.display = 'block';
                    fullscreenImg.style.display = 'none';
                }}
            }}
        }});
    </script>
    """
    return html_code


def add_to_recent(position, stack_size, action=None):
    """Add search to recent searches"""
    combo = f"{position} | {stack_size} | {action or 'None'}"
    if combo in st.session_state.recent_searches:
        st.session_state.recent_searches.remove(combo)
    st.session_state.recent_searches.insert(0, combo)
    st.session_state.recent_searches = st.session_state.recent_searches[:10]


def display_charts(filtered_df):
    """Display filtered charts with optimized sizing and spacing"""
    if filtered_df.empty:
        st.warning("No matching charts found.")
        return

    is_hu_mode = len(filtered_df) > 1 and st.session_state.selected_position == "HU"

    for idx, (_, row) in enumerate(filtered_df.iterrows()):
        file_path = row['file_path']
        filename = row['filename']

        # Create large image with controlled height
        large_image_html = create_large_image_html(file_path, caption=filename)
        if large_image_html:
            # Reduced overall component height to avoid scrolling
            st.components.v1.html(large_image_html, height=380, scrolling=False)

            if is_hu_mode:
                # Minimal image caption centered and compact
                st.markdown(
                    f"<div style='text-align:center; font-size:12px; margin-top:2px; margin-bottom:4px; color:gray;'>{filename}</div>",
                    unsafe_allow_html=True
                )
            else:
                # Show favorites button for non-HU charts
                fav_key = f"{st.session_state.selected_position}/{filename}"
                if fav_key not in st.session_state.favorites:
                    safe_key = hashlib.md5(str(file_path).encode()).hexdigest()
                    if st.button(f"⭐ Add to favorites: {filename}", key=f"fav_{safe_key}"):
                        st.session_state.favorites.append(fav_key)
                        add_to_recent(
                            st.session_state.selected_position,
                            st.session_state.selected_stack,
                            st.session_state.selected_action
                        )
                        st.success(f"Added {filename} to favorites!")
                        st.rerun()
                else:
                    st.info(f"⭐ Already in favorites: {filename}")

            # Minimal spacing between charts
            if idx < len(filtered_df) - 1:
                st.markdown('<div style="margin: 4px 0;"></div>', unsafe_allow_html=True)


def main():
    # Initialize session state
    init_session_state()

    # Page configuration
    st.set_page_config(
        page_title="Super Duper PCL",
        page_icon="🃏",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Enhanced CSS for better styling and optimized sidebar
    st.markdown("""
    <style>
    /* Sidebar title styling - centered and prominent */
    .sidebar-title {
        text-align: center !important;
        font-size: 20px !important;
        font-weight: 700 !important;
        color: #262730 !important;
        margin-bottom: 1.5rem !important;
        margin-top: 0 !important;
        padding: 1rem 0 !important;
        border-bottom: 2px solid #f0f0f0 !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        background-clip: text !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
    }

    /* Position button styling - keep original size and prominence */
    .position-button {
        width: 100%;
        margin: 2px 0;
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.2s ease;
        height: 32px !important;
        font-size: 14px !important;
        padding: 0 12px !important;
        line-height: 1.3 !important;
    }

    /* Stack size button styling - medium size for good balance */
    .stack-button {
        width: 100%;
        margin: 1px 0;
        border-radius: 5px;
        font-weight: 500;
        transition: all 0.2s ease;
        height: 30px !important;
        font-size: 12px !important;
        padding: 0 8px !important;
        line-height: 1.2 !important;
    }

    /* General button hover effect */
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    }

    /* Stack size buttons in 2-column grid */
    .stack-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 3px;
        margin-bottom: 8px;
    }

    /* Optimize main content spacing */
    .main .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
        max-width: 100% !important;
    }

    /* Compact sidebar with better organization */
    div[data-testid="stSidebar"] > div {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }

    /* Section headers in sidebar */
    .sidebar-section {
        margin-top: 1rem !important;
        margin-bottom: 0.5rem !important;
        font-size: 14px !important;
        font-weight: 600 !important;
        color: #262730 !important;
    }

    /* Search input styling */
    .stTextInput > div > div > input {
        font-size: 13px !important;
        padding: 8px 12px !important;
        border-radius: 5px !important;
    }

    /* Selectbox styling */
    .stSelectbox > div > div > select {
        font-size: 13px !important;
        padding: 6px 8px !important;
    }

    /* Remove extra spacing from headers */
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }

    /* Compact image containers */
    .large-chart-image {
        margin-bottom: 4px !important;
    }

    /* Reduce info/warning message spacing */
    .stAlert {
        margin-top: 0.25rem !important;
        margin-bottom: 0.25rem !important;
    }

    /* Compact metrics */
    .stMetric {
        margin-bottom: 0.25rem !important;
    }

    /* Remove default streamlit padding */
    .stApp > header {
        display: none;
    }
    </style>
    """, unsafe_allow_html=True)

    # Load images and metadata
    with st.spinner("Loading charts..."):
        images, df = load_images(PARENT_DIR)

    if not images:
        st.error(f"No PNG files found in {PARENT_DIR} or its subdirectories.")
        st.info("Please check if the directory path is correct and contains PNG files.")
        return

    # === SIDEBAR SECTION ===
    with st.sidebar:
        st.subheader("🎯 Position Selection")

        positions = ["BB", "SB", "BTN", "HU"]
        cols = st.columns(len(positions))

        for i, pos in enumerate(positions):
            with cols[i]:
                button_type = "primary" if st.session_state.selected_position == pos else "secondary"
                if st.button(pos, key=f"pos_{pos}", type=button_type):
                    st.session_state.selected_position = pos
                    st.session_state.selected_stack = None
                    st.session_state.selected_action = None
                    st.session_state.search_query = ''
                    st.session_state.show_results = False
                    st.rerun()

        # 🎲 Stack selection
        if st.session_state.selected_position:
            st.markdown('<div class="sidebar-section">🎲 Stack Size</div>', unsafe_allow_html=True)

            if st.session_state.selected_position == "HU":
                stack_buttons = [f"{i}bb" for i in range(3, 13)]
                cols = st.columns(2)
                for i, stack in enumerate(stack_buttons):
                    with cols[i % 2]:
                        if st.button(stack, key=f"hu_stack_{stack}"):
                            st.session_state.selected_stack = stack
                            st.session_state.selected_action = None
                            st.session_state.show_results = True
                            st.rerun()
                if st.session_state.selected_stack:
                    st.subheader("🔍 Action Filter")

                    hu_actions = df[
                        (df['hu'] == True) &
                        (df['stack_size'] == st.session_state.selected_stack)
                        ]['actions'].dropna().unique().tolist()

                    # Prepare possible actions (exclude 'None')
                    possible_actions = sorted(set(
                        a.strip() for a in hu_actions if a.strip().lower() != "none"
                    ))

                    action_input = st.text_input(
                        "Type action (e.g. SB limp or BB shove)", key="action_input_hu"
                    )

                    # Suggest matching actions as buttons
                    matching = [
                        a for a in possible_actions if
                        action_input.lower() in a.lower() and a.lower() != action_input.lower()
                    ]

                    button_selection_key = "selected_action_button_hu"
                    for a in matching[:5]:  # limit to 5 suggestions
                        if st.button(a, key=f"{button_selection_key}_{a}"):
                            st.session_state.selected_action = a
                            st.session_state.show_results = True
                            st.session_state[button_selection_key] = a
                            st.rerun()

                    # Fallback to typed input if no button was clicked
                    if not st.session_state.get(button_selection_key):
                        final_action = action_input
                        st.session_state.selected_action = final_action

                        if final_action and final_action.lower() in [a.lower() for a in possible_actions]:
                            st.session_state.show_results = True
            else:
                stack_options = [f"{i}bb" for i in range(5, 26)]
                default_stack = (
                    st.session_state.selected_stack
                    if st.session_state.selected_stack in stack_options
                    else stack_options[5]
                )

                selected_stack = st.selectbox(
                    "Select stack size:",
                    stack_options,
                    index=stack_options.index(default_stack)
                )

                if selected_stack != st.session_state.selected_stack:
                    st.session_state.selected_stack = selected_stack
                    st.session_state.selected_action = None  # reset action when stack changes
                    st.session_state.show_results = False
                    st.rerun()  # ✅ needed to trigger new suggestions/input behavior

        # 🔍 Action input (only for BB/SB/BTN)
        if st.session_state.selected_position in ["BB", "SB", "BTN"] and st.session_state.selected_stack:
            st.subheader("🔍 Action Filter")

            # Filter dataframe to get available actions for current position/stack
            actions_df = df[
                (df['hero_position'] == st.session_state.selected_position) &
                (df['stack_size'] == st.session_state.selected_stack)
                ]

            # For BB and SB positions, exclude HU files from available actions
            if st.session_state.selected_position in ["BB", "SB"]:
                actions_df = actions_df[actions_df['hu'] == False]

            possible_actions = actions_df['actions'].dropna().unique().tolist()

            # Filter out "None" actions and clean up the list
            possible_actions = [a.strip() for a in possible_actions if a.strip() and a.strip().lower() != 'none']
            possible_actions = sorted(set(possible_actions))

            # Create a unique key that changes when position/stack changes
            text_input_key = f"action_input_{st.session_state.selected_position}_{st.session_state.selected_stack}"

            # Check if a button was clicked (stored in a separate session state key)
            button_selection_key = f"button_selected_{st.session_state.selected_position}_{st.session_state.selected_stack}"

            # Primary text input for typing
            action_input = st.text_input(
                "Type action (start typing to filter suggestions):",
                key=text_input_key,
                placeholder="e.g., BTN, SB c, shove..."
            )

            # Show filtered suggestions based on what user is typing
            if possible_actions and action_input:
                # Filter actions that contain the typed text (case insensitive)
                filtered_actions = [
                    action for action in possible_actions
                    if action_input.lower() in action.lower()
                ]

                if filtered_actions:
                    st.write("**Matching actions:**")
                    # Show filtered actions in a more compact way
                    if len(filtered_actions) <= 6:
                        # Show as columns if few results
                        cols = st.columns(min(3, len(filtered_actions)))
                        for i, action in enumerate(filtered_actions):
                            with cols[i % 3]:
                                if st.button(f"✓ {action}", key=f"filtered_{i}_{text_input_key}", type="secondary"):
                                    # Store button selection in session state and trigger rerun
                                    st.session_state[button_selection_key] = action
                                    st.session_state.selected_action = action
                                    st.session_state.show_results = True
                                    st.rerun()
                    else:
                        # Show as a selectbox if many results
                        selected_from_filter = st.selectbox(
                            "Select from filtered results:",
                            options=[""] + filtered_actions,
                            key=f"filter_select_{text_input_key}"
                        )
                        if selected_from_filter:
                            st.session_state[button_selection_key] = selected_from_filter
                            st.session_state.selected_action = selected_from_filter
                            st.session_state.show_results = True
                            st.rerun()

            elif possible_actions and not action_input:
                # Show all actions when nothing is typed yet
                st.write(f"**Available actions ({len(possible_actions)}):**")
                if len(possible_actions) <= 8:
                    # Show as buttons if manageable number
                    cols = st.columns(min(4, len(possible_actions)))
                    for i, action in enumerate(possible_actions):
                        with cols[i % 4]:
                            if st.button(f"{action}", key=f"all_{i}_{text_input_key}", type="secondary"):
                                # Store button selection in session state and trigger rerun
                                st.session_state[button_selection_key] = action
                                st.session_state.selected_action = action
                                st.session_state.show_results = True
                                st.rerun()
                else:
                    # Show count and first few examples
                    st.write(f"Start typing to filter from {len(possible_actions)} actions...")
                    st.caption(
                        "Examples: " + ", ".join(possible_actions[:5]) + ("..." if len(possible_actions) > 5 else ""))

            # Handle button selections vs text input
            if st.session_state.get(button_selection_key):
                # Button was clicked - use that selection
                final_action = st.session_state[button_selection_key]
                # Clear the button selection after using it
                st.session_state[button_selection_key] = None
            else:
                # Use text input
                final_action = action_input

            # Update session state when action changes
            if final_action != st.session_state.get('selected_action', ''):
                st.session_state.selected_action = final_action
                if final_action and final_action.strip():
                    st.session_state.show_results = True

        # Recent Searches
        if st.session_state.recent_searches:
            st.markdown('<div class="sidebar-section">🕒 Recent Searches</div>', unsafe_allow_html=True)
            for recent in st.session_state.recent_searches[:5]:  # Show only 5 most recent
                if st.button(recent, key=f"recent_{recent}"):
                    parts = recent.split(" | ")
                    st.session_state.selected_position = parts[0]
                    st.session_state.selected_stack = parts[1]
                    st.session_state.selected_action = None if parts[2] == "None" else parts[2]
                    st.session_state.show_results = True
                    st.rerun()

        # Favorites
        if st.session_state.favorites:
            st.markdown('<div class="sidebar-section">⭐ Favorites</div>', unsafe_allow_html=True)
            for fav in st.session_state.favorites[:5]:  # Show only 5 favorites
                if st.button(fav, key=f"favorite_{fav}"):
                    parts = fav.split("/")
                    st.session_state.selected_position = parts[0]
                    st.session_state.show_results = True
                    st.rerun()

    # === MAIN PAGE ===
    if st.session_state.selected_position and st.session_state.selected_stack:
        filtered_df = df[df['stack_size'] == st.session_state.selected_stack]

        if st.session_state.selected_position == "HU":
            # For HU position, only show files that are marked as HU
            filtered_df = filtered_df[filtered_df['hu'] == True]

            none_action_charts = filtered_df[
                (filtered_df['actions'].isna()) |
                (filtered_df['actions'].str.strip().str.lower() == 'none') |
                (filtered_df['actions'].str.strip() == '')
                ]

            if st.session_state.selected_action and st.session_state.selected_action.strip():
                filtered_df = filtered_df[
                    filtered_df['actions'].str.lower().str.strip() ==
                    st.session_state.selected_action.lower().strip()
                    ]
            elif not none_action_charts.empty:
                filtered_df = none_action_charts
                st.session_state.show_results = True
            else:
                if not st.session_state.get("show_results"):
                    filtered_df = pd.DataFrame()
        else:
            # For BB, SB, BTN positions, exclude files with HU in the filename
            filtered_df = filtered_df[filtered_df['hero_position'] == st.session_state.selected_position]

            # Exclude HU files for BB and SB positions
            if st.session_state.selected_position in ["BB", "SB"]:
                filtered_df = filtered_df[filtered_df['hu'] == False]

            # Check if there are any charts with "None" actions for this position/stack
            none_action_charts = filtered_df[
                (filtered_df['actions'].isna()) |
                (filtered_df['actions'].str.strip().str.lower() == 'none') |
                (filtered_df['actions'].str.strip() == '')
                ]

            # If user has selected a specific action, filter by it
            if st.session_state.selected_action and st.session_state.selected_action.strip():
                filtered_df = filtered_df[
                    filtered_df['actions'].str.lower() == st.session_state.selected_action.lower()
                    ]
            # If no specific action selected, but there are "None" action charts, show them automatically
            elif not none_action_charts.empty:
                filtered_df = none_action_charts
                st.session_state.show_results = True
            # If no "None" action charts and no specific action selected, wait for user input
            else:
                # Only show results if explicitly requested
                if not st.session_state.get("show_results"):
                    filtered_df = pd.DataFrame()  # Empty results until action is selected

        # Remove duplicates
        if not filtered_df.empty:
            filtered_df = filtered_df.drop_duplicates(subset="file_path")

        # Sort HU charts so SB always appears before BB
        if st.session_state.selected_position == "HU" and not filtered_df.empty:
            position_order = {"SB":0, "BB":1}
            filtered_df = filtered_df.copy()
            filtered_df["_sort_key"] = filtered_df["filename"].apply(
                lambda x: next((v for k, v in position_order.items() if k in x.upper()),99)
            )
            filtered_df = filtered_df.sort_values("_sort_key").drop(columns=["_sort_key"])
        # Display results
        if st.session_state.get("show_results") and not filtered_df.empty:
            display_charts(filtered_df)
            add_to_recent(
                st.session_state.selected_position,
                st.session_state.selected_stack,
                st.session_state.selected_action
            )
        elif st.session_state.get("show_results") and filtered_df.empty:
            st.warning("No charts found matching your selection.")
        else:
            st.info("👈 Use the sidebar to select a position and filters, then click 'Show Charts'.")

            # Show statistics - more compact
            if not df.empty:
                st.markdown("**📊 Chart Statistics**")
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Total Charts", len(df))
                with col2:
                    st.metric("Positions", df['hero_position'].nunique())
                with col3:
                    st.metric("Stack Sizes", df['stack_size'].nunique())


if __name__ == "__main__":
    main()