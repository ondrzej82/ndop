import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import folium_static
from folium.plugins import HeatMap
from datetime import datetime
import os
import math

# Pro transformaci souřadnic z EPSG:5514 na WGS84 (EPSG:4326)
from pyproj import Transformer

# -------------------------------------------------------------
# KÓD S PODPOROU ENCODING CP1250
# -------------------------------------------------------------
#   1) Datum je ve formátu YYYYMMDD (parsováno přes %Y%m%d)
#   2) Souřadnice EPSG:5514 -> WGS84
#   3) Změna encodingu na cp1250 (místo utf-8-sig)
#   4) Přidáno low_memory=False, abychom předešli DtypeWarning
# -------------------------------------------------------------

# ========================
# Konfigurace sloupců:
# ========================

CONFIG = {
    # Sloupec s datem od (YYYYMMDD):
    'col_date': 'DATUM_OD',
    # Sloupec s datem do (YYYYMMDD):
    'col_date2': 'DATUM_DO',
    # Sloupec s názvem druhu:
    'col_species': 'CESKE_JMENO',
    # Sloupec s pozorovateli:
    'col_observer': 'AUTOR',
    # Sloupec s názvem města/obce:
    'col_city': 'KATASTR',
    # Sloupec s názvem místa pozorování:
    'col_location_name': 'NAZ_LOKAL',
    # Sloupec s minimálním počtem jedinců (pokud existuje):
    'col_count_min': 'POCET',
    # Sloupec s počtem (pokud existuje):
    'col_count': 'POCET',
    # Sloupec s odkazem (ID):
    'col_link': 'ID_NALEZ',
    # Sloupec kvadrátem:
    'col_kvadrat': 'SITMAP',
    # Sloupec se souřadnicí X (EPSG:5514):
    'col_lng': 'X',
    # Sloupec se souřadnicí Y (EPSG:5514):
    'col_lat': 'Y',
    # Nepovinný sloupec s aktivitou (pokud CSV obsahuje):
    'col_activity': 'Activity',
}

# ========================
# Nastavení Streamlit aplikace
# ========================
st.set_page_config(page_title="Statistika pozorování", layout="wide")

# Cesta k souboru CSV (lze nahradit jiným způsobem, např. upload přes st.file_uploader)
FILE_PATH = "uploaded_file.csv"
#https://drive.google.com/file/d/1aZF_k46UCLIXHj8HGrclXntiT3AsM2rO/view?usp=drive_link
# ID souboru na Google Drive (pokud nechcete používat Google Drive, stačí vymazat)
FILE_ID = "1aZF_k46UCLIXHj8HGrclXntiT3AsM2rO"
FILE_URL = f"https://drive.google.com/uc?id={FILE_ID}"

# ========================
# Funkce pro načtení dat z CSV
# ========================
@st.cache_data
def load_data(file_path: str) -> pd.DataFrame:
    """
    Načte a připraví data z CSV na základě sloupců definovaných v CONFIG.
    Nově: encoding cp1250 a low_memory=False
    """
    try:
        df = pd.read_csv(
            file_path,
            delimiter=';',
            encoding='utf-8-sig',  # ZMĚNA NA CP1250
            low_memory=False    # Zamezení DtypeWarning
        )
        if df.empty:
            st.error("Nahraný soubor je prázdný. Nahrajte prosím platný CSV soubor.")
            st.stop()
    except pd.errors.EmptyDataError:
        st.error("Soubor je prázdný nebo neplatný. Nahrajte prosím platný CSV soubor.")
        st.stop()

    # Převod a sjednocení názvů sloupců dle CONFIG
    rename_dict = {
        CONFIG['col_date']: "Datum",
        CONFIG['col_date2']: "Datum2",
        CONFIG['col_observer']: "Pozorovatel",
        CONFIG['col_city']: "Město",
        CONFIG['col_location_name']: "Místo pozorování",
        CONFIG['col_count_min']: "Počet_min",
        CONFIG['col_count']: "Počet",
        CONFIG['col_kvadrat']: "Kvadrát",
        CONFIG['col_link']: "Odkaz",
        CONFIG['col_lat']: "SouradniceY",
        CONFIG['col_lng']: "SouradniceX",
        CONFIG['col_species']: "Druh"
    }

    # Sloupce, které neexistují, ignorujeme (aby to nespadlo, pokud v CSV nejsou)
    rename_dict = {old: new for old, new in rename_dict.items() if old in df.columns}
    df.rename(columns=rename_dict, inplace=True)

    # 1) Převod datumu (YYYYMMDD) -> datetime
    if "Datum" in df.columns:
        df["Datum"] = pd.to_datetime(df["Datum"], format="%Y%m%d", errors="coerce")

    # 1a) Převod datumu (YYYYMMDD) -> datetime
    if "Datum2" in df.columns:
        df["Datum2"] = pd.to_datetime(df["Datum2"], format="%Y%m%d", errors="coerce")


    # 2) Pokud máme souřadnice ve sloupcích SouradniceX a SouradniceY, převedeme je na číslo
    if "SouradniceX" in df.columns:
        df["SouradniceX"] = pd.to_numeric(df["SouradniceX"], errors="coerce")
    if "SouradniceY" in df.columns:
        df["SouradniceY"] = pd.to_numeric(df["SouradniceY"], errors="coerce")

    # 3) Transformace souřadnic (EPSG:5514 -> WGS84)
    if "SouradniceX" in df.columns and "SouradniceY" in df.columns:
        transformer = Transformer.from_crs("EPSG:5514", "EPSG:4326", always_xy=True)
        # always_xy=True => (x, y) = (lon, lat)
        # V EPSG:5514 je X = Easting, Y = Northing, transform vrátí (lon, lat) v EPSG:4326
        lon_list, lat_list = transformer.transform(df["SouradniceX"].values, df["SouradniceY"].values)
        # Uložíme do dvou nových sloupců:
        df["Zeměpisná délka"] = lon_list
        df["Zeměpisná šířka"] = lat_list
    else:
        # Pokud neexistují X/Y, jen je vytvoříme prázdné
        df["Zeměpisná délka"] = None
        df["Zeměpisná šířka"] = None

    # Pokud sloupec Odkaz (ID) existuje, vytvoříme reálnou URL do sloupce
    if "Odkaz" in df.columns:
        df["Odkaz"] = df["Odkaz"].apply(
            lambda x: f'<a href="https://portal23.nature.cz/nd/find.php?akce=view&akce2=stopValidaci&karta_id={x}" target="_blank">link</a>' if pd.notna(x) else ""
        )

    # Sloupce s počty, pokud existují
    if "Počet" in df.columns:
        df["Počet"].fillna(1, inplace=True)
        df["Počet"] = df["Počet"].astype(int)

    if "Počet_min" in df.columns:
        df["Počet_min"].fillna(1, inplace=True)
        df["Počet_min"] = df["Počet_min"].astype(int)

    # Vyčištění nepovinných sloupců, pokud existují
    for col in ["Město", "Pozorovatel", "Místo pozorování", "Druh", "Kvadrát"]:
        if col in df.columns:
            df[col].fillna("", inplace=True)

    # Reset indexu
    df = df.reset_index(drop=True)

    return df


# ========================
# Funkce pro stažení a uložení souboru z Google Drive (volitelné)
# ========================
@st.cache_data
def load_data_from_drive():
    """
    Pokud chcete používat Google Drive, tato funkce stáhne CSV z drive.
    V opačném případě ji můžete vynechat a data nahrávat rovnou z disku
    nebo přes st.file_uploader.
    """
    import gdown
    if not os.path.exists(FILE_PATH):
        gdown.download(FILE_URL, FILE_PATH, quiet=False)
    return load_data(FILE_PATH)


# ========================
# Načtení (nebo stažení) dat
# ========================
df = load_data_from_drive()  # Pro data z Google Drive
# df = load_data(FILE_PATH)  # Pro data z lokálního souboru (alternativa)


# ========================
# Příprava checkboxů pro volitelné grafy / mapy
# ========================
c1, c2, c3, c4 = st.columns(4)
with c1:
    show_bar_yearly = st.checkbox("Graf: Počet druhů v jednotlivých letech", value=True)
with c2:
#    show_pie_top_species = st.checkbox("Koláč: Nejčastější druhy", value=True)
    show_bar_species_yearly = st.checkbox("Graf: Počet pozorování vybraného druhu", value=True)
with c3:
#    show_map_markers = st.checkbox("Mapa s body pozorování", value=True)
    show_map_heat = st.checkbox("Heatmapa pozorování", value=True)
with c4:
    show_bar_monthly_obs = st.checkbox("Graf: Počty pozorování podle měsíců", value=True)


# ========================
# Definice proměnných pro sloupce v aplikaci
# (abychom se nemuseli spoléhat na "tvrdé" názvy sloupců)
# ========================
COL_DATE = "Datum"
COL_DATE2 = "Datum2"
COL_SPECIES = "Druh"
COL_LAT = "Zeměpisná šířka"
COL_LNG = "Zeměpisná délka"
COL_COUNT = "Počet"


# ========================
# Filtr: Druh
# ========================
species_list = ["Vyber"]
if df is not None and not df.empty and COL_SPECIES in df.columns:
    species_list = ["Vyber"] + sorted(set(df[COL_SPECIES].dropna().unique()))
selected_species = st.selectbox("Vyberte druh:", species_list)

# ========================
# Filtr: Datum (Rok nebo vlastní rozsah)
# ========================
if COL_DATE in df.columns and not df.empty:
    date_min = df[COL_DATE].min().date()
    date_max = df[COL_DATE].max().date()
    years = sorted(df[COL_DATE].dropna().dt.year.unique())
else:
    date_min = datetime.today().date()
    date_max = datetime.today().date()
    years = []

selected_year = st.selectbox("Vyberte rok:", ["Vlastní rozsah"] + [str(y) for y in years])

if selected_year == "Vlastní rozsah":
    col_date_from, col_date_to = st.columns(2)
    with col_date_from:
        date_from = st.date_input("Datum od:", date_min, min_value=date_min, max_value=date_max)
    with col_date_to:
        date_to = st.date_input("Datum do:", date_max, min_value=date_min, max_value=date_max)
else:
    # Pokud uživatel vybral rok, bereme 1.1. a 31.12. daného roku
    try:
        selected_year_int = int(selected_year)
        date_from = datetime(selected_year_int, 1, 1).date()
        date_to = datetime(selected_year_int, 12, 31).date()
    except:
        # Pro jistotu fallback:
        date_from = date_min
        date_to = date_max

# ========================
# Filtrování dat
# ========================
filtered_data = df.copy()

if not filtered_data.empty and COL_DATE in filtered_data.columns:
    filtered_data = filtered_data[
        (filtered_data[COL_DATE].dt.date >= date_from) &
        (filtered_data[COL_DATE].dt.date <= date_to)
    ]

if selected_species == "Vyber":
    # Když není vybraný žádný konkrétní druh, vyprázdníme data:
    filtered_data = filtered_data.iloc[0:0]
elif selected_species != "Vyber":
    # Filtr na vybraný druh
    if COL_SPECIES in filtered_data.columns:
        filtered_data = filtered_data[filtered_data[COL_SPECIES] == selected_species]


# ========================
# Graf: Počet pozorovaných DRUHŮ v jednotlivých letech (z celých DF)
# ========================
if df is not None and not df.empty and COL_DATE in df.columns and COL_SPECIES in df.columns:
    yearly_counts = df.groupby(df[COL_DATE].dt.year)[COL_SPECIES].nunique().reset_index()
    yearly_counts.columns = ["Rok", "Počet druhů"]
else:
    yearly_counts = pd.DataFrame(columns=["Rok", "Počet druhů"])

fig_yearly = px.bar(
    yearly_counts,
    x="Rok",
    y="Počet druhů",
    title="Celkový počet pozorovaných druhů podle roku",
)

fig_yearly.update_xaxes(type='category')

# Podmínka pro zobrazení grafu pouze pokud je ve filtru vybráno "vyber"
if show_bar_yearly and selected_species == "Vyber":
 #   st.write("### Počet pozorovaných druhů v jednotlivých letech")
    st.plotly_chart(fig_yearly)

# ========================
# Graf: Počet pozorovaných DRUHŮ v jednotlivých letech (z celých DF)
# ========================
if df is not None and not df.empty and COL_DATE in df.columns and COL_SPECIES in df.columns:
    yearly_counts = df.groupby(df[COL_DATE].dt.year)[COL_SPECIES].nunique().reset_index()
    yearly_counts.columns = ["Rok", "Počet druhů"]
else:
    yearly_counts = pd.DataFrame(columns=["Rok", "Počet druhů"])

fig_yearly = px.bar(
    yearly_counts,
    x="Rok",
    y="Počet druhů",
    title="Celkový počet pozorovaných druhů podle roku",
)

fig_yearly.update_xaxes(type='category')

# Podmínka pro zobrazení grafu pouze pokud je ve filtru vybráno "vyber"
if show_bar_yearly and selected_species == "vyber":
    st.write("### Počet pozorovaných druhů v jednotlivých letech")
    st.plotly_chart(fig_yearly)

# Výpočet procentuálního výskytu druhu a četnosti záznamů na jedno pozorování
if selected_species != "vyber" and selected_species.strip():
    total_observations = len(df)
    species_observations = len(df[df[COL_SPECIES] == selected_species])
    if total_observations > 0 and species_observations > 0:
        species_percentage = (species_observations / total_observations) * 100
        st.markdown(f"""
        <div style='font-size: 25px; font-weight: bold;'>
            Druh {selected_species} tvoří {species_percentage:.2f}% všech záznamů.
        </div>
        <div style='font-size: 25px; font-weight: bold;'>
            1 z {total_observations // species_observations} pozorování je {selected_species}.
        </div>
        """, unsafe_allow_html=True)






# ========================
# Graf: Počet pozorování vybraného druhu v jednotlivých letech
# ========================
if selected_species not in ["Vyber", ""]:
    # Vytvoříme DataFrame se všemi roky, které máme v datech:
    all_years_df = pd.DataFrame({"Rok": years})
    # Spočítáme pro vybraný druh
    if COL_DATE in df.columns and COL_SPECIES in df.columns:
        yearly_species_counts = (
            df[df[COL_SPECIES] == selected_species]
            .groupby(df[COL_DATE].dt.year).size()
            .reset_index(name="Počet pozorování")
        )
        # Propojíme s tabulkou všech roků (aby se zobrazila i nula, kde není pozorování)
        yearly_species_counts = all_years_df.merge(
            yearly_species_counts, left_on="Rok", right_on=COL_DATE, how="left"
        ).fillna(0)

        # Datový typ
        yearly_species_counts["Počet pozorování"] = yearly_species_counts["Počet pozorování"].astype(int)

        fig_species_yearly = px.bar(
            yearly_species_counts,
            x="Rok",
            y="Počet pozorování",
            title=f"Počet pozorování druhu {selected_species} podle roku",
        )
        fig_species_yearly.update_xaxes(type='category')

        if show_bar_species_yearly:
         #   st.write(f"### Počet pozorování druhu {selected_species} v jednotlivých letech")
            st.plotly_chart(fig_species_yearly)




# ========================
# Mapa s body pozorování (MarkerCluster)
# ========================

#if show_map_markers:
#    if not filtered_data.empty and COL_LAT in filtered_data.columns and COL_LNG in filtered_data.columns:
#        # Střed mapy podle průměrné polohy
#        map_center = [
#            filtered_data[COL_LAT].mean(),
#            filtered_data[COL_LNG].mean()
#        ]
#    else:
#        # Fallback: střed ČR
#        map_center = [49.40099, 15.67521]
#
#    m = folium.Map(location=map_center, zoom_start=8.2)
#
#    if not filtered_data.empty:
#        from folium.plugins import MarkerCluster
#        marker_cluster = MarkerCluster().add_to(m)
#        for _, row in filtered_data.dropna(subset=[COL_LAT, COL_LNG]).iterrows():
#            # Popisek v bublině
#            popup_text = ""
#            if "Místo pozorování" in row and row["Místo pozorování"]:
#                popup_text += f"{row['Místo pozorování']}<br>"
#            if COL_COUNT in row and not pd.isna(row[COL_COUNT]):
#                popup_text += f"Počet: {row[COL_COUNT]}"
#            folium.Marker(
#                location=[row[COL_LAT], row[COL_LNG]],
#                popup=popup_text,
#            ).add_to(marker_cluster)
#
#        st.write("### Mapa pozorování (body)")
#        folium_static(m)
#    else:
#        st.info("Pro zobrazení nahoře vyberte druh.")

# ========================
# Heatmapa pozorování
# ========================
if show_map_heat:
    if not filtered_data.empty and COL_LAT in filtered_data.columns and COL_LNG in filtered_data.columns:
        map_center = [
            filtered_data[COL_LAT].mean(),
            filtered_data[COL_LNG].mean()
        ]
    else:
        map_center = [49.40099, 15.67521]

    heat_map = folium.Map(location=map_center, zoom_start=8)

    # 🔹 Přidání dalších volitelných vrstev (Esri, CartoDB)
    folium.TileLayer("Stamen Terrain", name="Topografická mapa").add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="Tmavá mapa").add_to(m)
    
    if not filtered_data.empty:
        heat_df = filtered_data.dropna(subset=[COL_LAT, COL_LNG])
        # Pokud máme i počty, můžeme je sečíst
        if COL_COUNT in heat_df.columns:
            heat_agg = heat_df.groupby([COL_LAT, COL_LNG])[COL_COUNT].sum().reset_index()
        else:
            # Pokud nemáme počty, dáme "1" za každé pozorování
            heat_df["pocty"] = 1
            heat_agg = heat_df.groupby([COL_LAT, COL_LNG])["pocty"].sum().reset_index()

        heat_data = heat_agg.values.tolist()
        HeatMap(heat_data, radius=10).add_to(heat_map)

        st.write("### Mapa pozorování")
        folium_static(heat_map)
    else:
        st.info("Pro zobrazení nahoře vyberte druh.")



# ========================
# Grafy podle měsíců
# ========================
if not filtered_data.empty and COL_DATE in filtered_data.columns and COL_DATE2 in filtered_data.columns:
    # Filtrovat pouze záznamy, kde COL_DATE a COL_DATE2 jsou ve stejném měsíci
    filtered_data = filtered_data[
        (filtered_data[COL_DATE].dt.month == filtered_data[COL_DATE2].dt.month) &
        (filtered_data[COL_DATE].dt.year == filtered_data[COL_DATE2].dt.year)
    ]

    if not filtered_data.empty:  # Zkontrolujeme, zda po filtraci nejsou data prázdná
        # Přidáme textový název měsíce
        filtered_data["Měsíc"] = filtered_data[COL_DATE].dt.month.map({
            1: "Leden", 2: "Únor", 3: "Březen", 4: "Duben", 5: "Květen", 6: "Červen",
            7: "Červenec", 8: "Srpen", 9: "Září", 10: "Říjen", 11: "Listopad", 12: "Prosinec"
        })

        # Spočítáme počty pozorování a jedinců
        group_dict = {COL_DATE: "count"}
        if COL_COUNT in filtered_data.columns:
            group_dict[COL_COUNT] = "sum"

        monthly_counts = filtered_data.groupby("Měsíc").agg(group_dict).reset_index()

        # Přejmenujeme sloupce
        monthly_counts.rename(columns={
            COL_DATE: "Počet pozorování",
            COL_COUNT: "Počet jedinců" if COL_COUNT in filtered_data.columns else "Počet jedinců (není ve sloupci)"
        }, inplace=True)

        # Vytvoříme rámec se všemi měsíci (pro správné seřazení a zobrazení i tam, kde jsou 0)
        all_months_df = pd.DataFrame({
            "Měsíc": [
                "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
                "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec"
            ]
        })

        # Sloučíme a vyplníme nuly
        monthly_counts = all_months_df.merge(monthly_counts, on="Měsíc", how="left").fillna(0)
        monthly_counts["Počet pozorování"] = monthly_counts["Počet pozorování"].astype(int)
        if "Počet jedinců" in monthly_counts.columns:
            monthly_counts["Počet jedinců"] = monthly_counts["Počet jedinců"].astype(int)

        # GRAF: Počet pozorování podle měsíců
        if show_bar_monthly_obs:
            fig_monthly_obs = px.bar(
                monthly_counts,
                x="Měsíc",
                y="Počet pozorování",
                title="Počet pozorování podle měsíců"
            )
#            st.write("### Počet pozorování podle měsíců")
            st.plotly_chart(fig_monthly_obs)

        # (Případně druhý graf pro Počet jedinců)
        # fig_monthly_counts = px.bar(
        #     monthly_counts,
        #     x="Měsíc",
        #     y="Počet jedinců",
        #     title="Počet jedinců podle měsíců"
        # )
        # st.plotly_chart(fig_monthly_counts)
    else:
        st.info("Žádná data po filtrování pro vykreslení grafu.")

# ========================
# Výpis tabulky s HTML odkazem + STRÁNKOVÁNÍ (100 záznamů na stránku)
# ========================
st.write(f"### Pozorování druhu: {selected_species}")

if not filtered_data.empty:
    # Kopie jen pro úpravu zobrazení
    filtered_data_display = filtered_data.copy()

    # Pokud sloupce existují, můžeme je zkracovat atd.
    if "Místo pozorování" in filtered_data_display.columns:
        filtered_data_display["Místo pozorování"] = filtered_data_display["Místo pozorování"].apply(
            lambda x: (x[:50] + "...") if isinstance(x, str) and len(x) > 50 else x
        )
    if "Pozorovatel" in filtered_data_display.columns:
        filtered_data_display["Pozorovatel"] = filtered_data_display["Pozorovatel"].apply(
            lambda x: (x[:50] + "...") if isinstance(x, str) and len(x) > 50 else x
        )
    if "Datum" in filtered_data_display.columns:
        filtered_data_display["Datum"] = filtered_data_display["Datum"].apply(
            lambda x: x.strftime('%d. %m. %Y') if pd.notna(x) else ''
        )

    # Stránkování
    page_size = 300
    if "page_number" not in st.session_state:
        st.session_state.page_number = 1

    total_rows = len(filtered_data_display)
    n_pages = math.ceil(total_rows / page_size)

#Horní tlačítka
    col_pag_left, col_pag_mid, col_pag_right = st.columns([1,2,1])

    with col_pag_left:
        if st.button("← Předchozí", key="prev_bottom"):
            if st.session_state.page_number > 0:
                st.session_state.page_number -= 1

    with col_pag_mid:
        st.write(f"Stránka {st.session_state.page_number + 1} / {n_pages}")

    with col_pag_right:
        if st.button("Další →", key="next_bottom"):
            if st.session_state.page_number < n_pages - 1:
                st.session_state.page_number += 1

    start_idx = st.session_state.page_number * page_size
    end_idx = start_idx + page_size

    limited_data = filtered_data_display.iloc[start_idx:end_idx]

    columns_to_show = []
    for col in ["Datum", "Počet", "Místo pozorování", "Město", "Pozorovatel", "Odkaz"]:
        if col in limited_data.columns:
            columns_to_show.append(col)

    st.write(
        limited_data[columns_to_show].to_html(index=False, escape=False),
        unsafe_allow_html=True
    )

#Dolní tlačítka


    col_pag_left, col_pag_mid, col_pag_right = st.columns([1,2,1])

    with col_pag_left:
        if st.button("← Předchozí", key="prev_top"):
            if st.session_state.page_number > 0:
                st.session_state.page_number -= 1

    with col_pag_mid:
        st.write(f"Stránka {st.session_state.page_number + 1} / {n_pages}")

    with col_pag_right:
        if st.button("Další →", key="next_top"):
            if st.session_state.page_number < n_pages - 1:
                st.session_state.page_number += 1
    start_idx = st.session_state.page_number * page_size
    end_idx = start_idx + page_size

else:
    st.info("Pro zobrazení nahoře vyberte druh.")
