import streamlit as st
import sqlite3
import bcrypt
import pandas as pd
import plotly.express as px
from PIL import Image
import base64
import io
from datetime import datetime
from prophet import Prophet
import streamlit.components.v1 as components

def angka_input_with_format(label, key="formatted_input"):
    st.markdown(f"<label>{label}</label>", unsafe_allow_html=True)
    html_code = f"""
    <script>
    function formatNumber(input) {{
        var value = input.value.replace(/[^0-9]/g, '');
        if (value) {{
            input.value = parseInt(value).toLocaleString('id-ID');
        }} else {{
            input.value = '';
        }}
    }}
    </script>
    <input id="{key}" type="text" oninput="formatNumber(this)" placeholder="Contoh: 100000" style="padding: 0.5rem; width: 100%; border-radius: 5px; border: 1px solid #ccc;">
    <script>
        const input = window.parent.document.getElementById("{key}");
        input?.addEventListener("input", function() {{
            const value = input.value.replaceAll('.', '');
            window.parent.postMessage({{ type: "streamlit:setComponentValue", key: "{key}", value: value }}, "*");
        }});
    </script>
    """
    value = components.html(html_code, height=60)
    return value

DB_NAME = "users.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def initialize_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        profile_pic BLOB,
        emergency_rate INTEGER DEFAULT 10
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS laporan_keuangan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        tanggal TEXT,
        kategori TEXT,
        jenis TEXT,
        jumlah INTEGER,
        dana_darurat INTEGER,
        keterangan TEXT,
        bukti_img BLOB
    )
    """)
    conn.commit()
    conn.close()

def register_user(username, password, role):
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username, password_hash, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def login_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode(), row[0]):
        return True, row[1]
    return False, None

def get_user_settings(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT emergency_rate, profile_pic FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result

def home_page():
    st.title("🏠 Home - Input Data Keuangan")

    # Inisialisasi atau update key untuk mereset form
    if "input_key" not in st.session_state:
        st.session_state["input_key"] = 0

    tanggal = st.date_input("Tanggal Transaksi", value=datetime.now().date(), key=f"tanggal_{st.session_state['input_key']}")
    
    # Menambahkan opsi 'Pilih' pada selectbox Jenis
    jenis = st.selectbox("Jenis", ["Pilih", "Pendapatan", "Pengeluaran"], key=f"jenis_{st.session_state['input_key']}")

    # Menentukan opsi kategori berdasarkan jenis yang dipilih, dan menambahkan 'Pilih'
    kategori_options = []
    if jenis == "Pilih":
        kategori_options = ["Pilih"]
    elif jenis == "Pendapatan":
        kategori_options = ["Pilih", "Keuntungan"]
    else: # jenis == "Pengeluaran"
        kategori_options = ["Pilih", "Listrik", "Gaji", "PDAM", "Bahan Baku", "Sewa Tempat", "Lain-lain"]
    
    kategori_index = 0
    if kategori_options and "Pilih" in kategori_options:
        kategori_index = kategori_options.index("Pilih")

    kategori = st.selectbox("Kategori", kategori_options, index=kategori_index, key=f"kategori_{st.session_state['input_key']}")

    def format_angka_indonesia(angka_str):
        try:
            # Handle empty string or string with only non-numeric characters
            if not any(char.isdigit() for char in angka_str):
                return angka_str
            angka = int(angka_str.replace(".", "").replace(",", ""))
            return "{:,.0f}".format(angka).replace(",", ".")
        except ValueError:
            return angka_str # Return original if conversion fails for non-numeric input

    jumlah_input = st.text_input("Jumlah (Rp)", placeholder="Contoh: 100000", key=f"jumlah_input_{st.session_state['input_key']}")

    if jumlah_input:
        formatted_display = format_angka_indonesia(jumlah_input)
        st.write(f"Jumlah diformat: **Rp {formatted_display}**")

    # Dana Darurat Settings
    
    username = st.session_state["username"]
    emergency_rate, _ = get_user_settings(username)
    new_rate = st.slider("Persentase Dana Darurat (%)", 5, 10, emergency_rate)
    if new_rate != emergency_rate:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET emergency_rate = ? WHERE username = ?", (new_rate, username))
        conn.commit()
        conn.close()
        st.success("✅ Persentase Dana Darurat berhasil diubah.")

    keterangan = st.text_input("Keterangan (Opsional)", key=f"keterangan_{st.session_state['input_key']}")

    bukti_img = None
    uploaded_img = st.file_uploader("Upload Bukti Gambar (opsional)", type=["png", "jpg", "jpeg"], key=f"bukti_img_{st.session_state['input_key']}")
    if uploaded_img:
        bukti_img = uploaded_img.read()


    if st.button("Simpan Data"):
        if not jumlah_input:
            st.warning("Jumlah tidak boleh kosong.")
            return
        if jenis == "Pilih":
            st.warning("Silakan pilih Jenis transaksi.")
            return
        if kategori == "Pilih":
            st.warning("Silakan pilih Kategori transaksi.")
            return

        try:
            jumlah = int(jumlah_input.replace(".", "").replace(",", ""))
            username = st.session_state["username"]
            emergency_rate, _ = get_user_settings(username)
            dana_darurat = int(jumlah * (emergency_rate / 100)) if jenis == "Pendapatan" else 0

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO laporan_keuangan (username, tanggal, kategori, jenis, jumlah, dana_darurat, keterangan, bukti_img)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (username, tanggal.isoformat(), kategori, jenis, jumlah, dana_darurat, keterangan, bukti_img))
            conn.commit()
            conn.close()
            st.success("✅ Data berhasil disimpan.")
            # Increment key to reset all input widgets
            st.session_state["input_key"] += 1
            st.rerun()
        except ValueError:
            st.error("Jumlah harus berupa angka valid, contoh: 100000")
        except Exception as e:
            st.error(f"Terjadi kesalahan: {e}")


def generate_forecasting_insights(df_forecast, periods, data_type):
    insights = []
    
    # Filter forecast to only include future predictions
    future_forecast = df_forecast.tail(periods)

    if future_forecast.empty:
        insights.append(f"Tidak ada data *forecast* {data_type} di masa depan untuk dianalisis.")
        return insights

    # Get the last historical value for comparison (from the part of df_forecast that's not future)
    # This needs to be robust, ensuring we get the actual last historical data point.
    # We assume 'ds' is sorted and the last 'periods' rows are the future.
    # So the last historical point would be just before the future period starts.
    if len(df_forecast) > periods:
        last_historical_value = df_forecast['yhat'].iloc[len(df_forecast) - periods - 1]
    else:
        # This case implies df_forecast largely consists of future data or very few historical points.
        # We need a robust way to get the last actual historical data point.
        # If 'y' column was preserved (which it isn't in 'forecast' output), we could use df_pendapatan['y'].iloc[-1].
        # For 'forecast' dataframe, we can assume the last non-future point is the one just before the prediction starts.
        # Or, if only future is available, the first prediction itself might serve as a baseline for trend.
        # For simplicity and robustnes here, we'll try to find the last historical 'yhat' in df_forecast.
        # This might not be ideal if df_forecast is mostly future, but works if it includes historical 'yhat' as well.
        last_historical_value = df_forecast['yhat'].iloc[max(0, len(df_forecast) - periods - 1)]

    # Calculate the average forecast for the future days
    avg_forecast_future = future_forecast['yhat'].mean()

    # Calculate the change from the last historical value to the end of the forecast period
    final_forecast_value = future_forecast['yhat'].iloc[-1]
    change = final_forecast_value - last_historical_value
    
    # Trend Analysis
    if change > 0:
        insights.append(f"{data_type.capitalize()} Anda diperkirakan akan menunjukkan **tren meningkat** dalam {periods} hari ke depan, dengan estimasi kenaikan sekitar **Rp {change:,.0f}** dari periode terakhir yang tercatat.")
    elif change < 0:
        insights.append(f"{data_type.capitalize()} Anda diperkirakan akan menunjukkan **tren menurun** dalam {periods} hari ke depan, dengan estimasi penurunan sekitar **Rp {abs(change):,.0f}** dari periode terakhir yang tercatat.")
    else:
        insights.append(f"{data_type.capitalize()} Anda diperkirakan akan **cenderung stabil** dalam {periods} hari ke depan.")

    # Volatility/Uncertainty Analysis
    # The range of uncertainty (yhat_upper - yhat_lower)
    avg_uncertainty_range = (future_forecast['yhat_upper'] - future_forecast['yhat_lower']).mean()
    if avg_forecast_future != 0: # Avoid division by zero
        if avg_uncertainty_range < abs(avg_forecast_future) * 0.1: # Example threshold: less than 10% of average forecast
            insights.append(f"Model menunjukkan **tingkat kepercayaan yang tinggi** terhadap prediksi ini, dengan rata-rata rentang ketidakpastian sekitar **Rp {avg_uncertainty_range:,.0f}** per hari.")
        elif avg_uncertainty_range < abs(avg_forecast_future) * 0.3: # Example threshold: less than 30%
            insights.append(f"Prediksi memiliki **tingkat kepercayaan moderat**, dengan rata-rata rentang ketidakpastian sekitar **Rp {avg_uncertainty_range:,.0f}** per hari. Fluktuasi kecil mungkin terjadi.")
        else:
            insights.append(f"Ada **ketidakpastian yang cukup tinggi** dalam prediksi ini, dengan rata-rata rentang ketidakpastian sekitar **Rp {avg_uncertainty_range:,.0f}** per hari. Ini bisa disebabkan oleh data historis yang bervariasi. Pertimbangkan untuk menambahkan lebih banyak data atau memeriksa anomali.")
    else:
        insights.append(f"Tidak dapat menganalisis volatilitas karena {data_type} rata-rata yang diperkirakan adalah nol.")

    # Seasonal Analysis (simple check for daily/weekly patterns if present)
    max_forecast_future = future_forecast['yhat'].max()
    min_forecast_future = future_forecast['yhat'].min()
    
    if avg_forecast_future != 0 and (max_forecast_future - min_forecast_future) > (abs(avg_forecast_future) * 0.2): # If fluctuation is more than 20% of avg
        insights.append(f"Terdapat indikasi **pola musiman** dalam {data_type}, dengan fluktuasi antara **Rp {min_forecast_future:,.0f}** dan **Rp {max_forecast_future:,.0f}** dalam {periods} hari ke depan. Perhatikan hari-hari atau periode tertentu yang mungkin memiliki {data_type} lebih tinggi atau lebih rendah.")
    else:
        insights.append(f"Pola musiman yang signifikan tidak terlalu terlihat dalam periode prediksi ini, menunjukkan {data_type} yang cenderung lebih konsisten dari hari ke hari.")

    return insights


def dashboard_page():
    st.title("📊 Dashboard Keuangan")
    username = st.session_state["username"]
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM laporan_keuangan WHERE username = ?", conn, params=(username,))
    conn.close()

    if df.empty:
        st.info("Tidak ada data.")
        return

    df["tanggal"] = pd.to_datetime(df["tanggal"])
    df["jenis"] = df["jenis"].str.lower()

    st.subheader("📂 Pilih Jenis Data")
    jenis_filter = st.selectbox("Tampilkan", ["Semua", "Pendapatan", "Pengeluaran"])

    if jenis_filter != "Semua":
        df = df[df["jenis"] == jenis_filter.lower()]
        if df.empty:
            st.info(f"Tidak ada data {jenis_filter.lower()} yang tersedia.")
            return

    # 🔎 Filter Kategori
    st.subheader("🏷️ Filter Kategori")
    kategori_unik = sorted(df["kategori"].unique())
    kategori_filter = st.selectbox("Pilih Kategori", ["Semua"] + kategori_unik)

    if kategori_filter != "Semua":
        df = df[df["kategori"] == kategori_filter]
        if df.empty:
            st.info("Tidak ada data untuk kategori tersebut.")
            return

    st.subheader("📅 Filter Waktu")
    filter_mode = st.selectbox("Filter Berdasarkan", ["Semua", "Hari", "Bulan", "Tahun", "Rentang Tanggal"])

    if filter_mode == "Hari":
        tanggal = st.date_input("Pilih Tanggal")
        df = df[df["tanggal"].dt.date == tanggal]
    elif filter_mode == "Bulan":
        bulan_list = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ]
        bulan = st.selectbox("Pilih Bulan", bulan_list)
        bulan_angka = bulan_list.index(bulan) + 1
        df = df[df["tanggal"].dt.month == bulan_angka]
    elif filter_mode == "Tahun":
        tahun = st.selectbox("Pilih Tahun", sorted(df["tanggal"].dt.year.unique()))
        df = df[df["tanggal"].dt.year == tahun]
    elif filter_mode == "Rentang Tanggal":
        rentang = st.date_input("Pilih Rentang", [])
        if len(rentang) == 2:
            df = df[(df["tanggal"] >= pd.to_datetime(rentang[0])) & (df["tanggal"] <= pd.to_datetime(rentang[1]))]

    if df.empty:
        st.info("Tidak ada data untuk filter yang dipilih.")
        return

    # Sesuaikan grafik berdasarkan filter jenis
    if jenis_filter == "Pendapatan":
        y_data = ["pendapatan"]
    elif jenis_filter == "Pengeluaran":
        y_data = ["pengeluaran"]
    else:
        y_data = ["pendapatan", "pengeluaran"]

    # Calculate sums for current view
    total_pendapatan = df[df["jenis"] == "pendapatan"]["jumlah"].sum()
    total_pengeluaran = df[df["jenis"] == "pengeluaran"]["jumlah"].sum()
    keuntungan_bersih = total_pendapatan - total_pengeluaran

    # Create a daily summary for charting
    daily_summary = df.groupby(["tanggal", "jenis"])["jumlah"].sum().unstack().fillna(0)
    if "pendapatan" not in daily_summary.columns:
        daily_summary["pendapatan"] = 0
    if "pengeluaran" not in daily_summary.columns:
        daily_summary["pengeluaran"] = 0
    daily_summary = daily_summary.reset_index()


    fig = px.line(daily_summary, x="tanggal", y=y_data, markers=True,
                    title="Tren Keuangan Harian",
                    labels={"value": "Jumlah", "tanggal": "Tanggal"},
                    color_discrete_map={"pendapatan": "#4CAF50", "pengeluaran": "#F44336"})
    st.plotly_chart(fig)

    # --- Modern & Minimalist Summary ---
    st.subheader("📋 Ringkasan Keuangan Anda")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(label="💰 Total Pendapatan", value=f"Rp {total_pendapatan:,.0f}".replace(",", "."))
        st.markdown(
            """
            <style>
            [data-testid="stMetricValue"] {
                font-size: 24px;
                color: #4CAF50; /* Green for positive */
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.metric(label="💸 Total Pengeluaran", value=f"Rp {total_pengeluaran:,.0f}".replace(",", "."))
        st.markdown(
            """
            <style>
            [data-testid="stMetricValue"] {
                font-size: 24px;
                color: #F44336; /* Red for negative */
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        if keuntungan_bersih >= 0:
            st.metric(label="📊 Keuntungan Bersih", value=f"Rp {keuntungan_bersih:,.0f}".replace(",", "."), delta="👍 Cukup Baik!" if keuntungan_bersih > 0 else None, delta_color="normal")
            st.markdown(
                """
                <style>
                [data-testid="stMetricValue"] {
                    font-size: 24px;
                    color: #2196F3; /* Blue for neutral/good */
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.metric(label="📊 Rugi Bersih", value=f"Rp {abs(keuntungan_bersih):,.0f}".replace(",", "."), delta="👎 Perlu Perhatian!" if keuntungan_bersih < 0 else None, delta_color="inverse")
            st.markdown(
                """
                <style>
                [data-testid="stMetricValue"] {
                    font-size: 24px;
                    color: #FF9800; /* Orange for caution */
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---") # Garis pemisah untuk estetika
    st.info(f"**Ringkasan ini mencakup data dari tanggal {df['tanggal'].min().strftime('%d %b %Y')} hingga {df['tanggal'].max().strftime('%d %b %Y')}.**")
    # --- End Modern & Minimalist Summary ---


    st.subheader("📈 Forecasting")
    
    # New selectbox for forecasting type
    forecast_type = st.selectbox("Pilih jenis data untuk Forecasting:", ["Pendapatan", "Pengeluaran", "Keuntungan (Pendapatan - Pengeluaran)"])
    
    # Slider for number of forecast days
    forecast_periods = st.slider("Pilih berapa hari ke depan untuk prediksi:", 1, 365, 30)
    
    # Button to run forecasting
    if st.button("Jalankan Forecasting"):
        df_for_forecast = pd.DataFrame()
        data_type_label = ""

        if forecast_type == "Pendapatan":
            df_for_forecast = df[df["jenis"] == "pendapatan"].copy()
            df_for_forecast = df_for_forecast.groupby("tanggal")["jumlah"].sum().reset_index()
            data_type_label = "pendapatan"
        elif forecast_type == "Pengeluaran":
            df_for_forecast = df[df["jenis"] == "pengeluaran"].copy()
            df_for_forecast = df_for_forecast.groupby("tanggal")["jumlah"].sum().reset_index()
            data_type_label = "pengeluaran"
        elif forecast_type == "Keuntungan (Pendapatan - Pengeluaran)":
            df_pendapatan_daily_df = df[df["jenis"] == "pendapatan"].groupby("tanggal")["jumlah"].sum().reset_index()
            df_pengeluaran_daily_df = df[df["jenis"] == "pengeluaran"].groupby("tanggal")["jumlah"].sum().reset_index()
            
            # Merge to get all dates and corresponding amounts
            merged_df = pd.merge(df_pendapatan_daily_df, df_pengeluaran_daily_df, 
                                 on='tanggal', how='outer', suffixes=('_pendapatan', '_pengeluaran'))
            
            # Fill NaN values with 0
            merged_df = merged_df.fillna(0)
            
            # Calculate net amount
            merged_df['jumlah'] = merged_df['jumlah_pendapatan'] - merged_df['jumlah_pengeluaran']
            
            df_for_forecast = merged_df[['tanggal', 'jumlah']]
            data_type_label = "keuntungan"

        df_for_forecast.columns = ["ds", "y"]  # Rename columns for Prophet
        df_for_forecast["ds"] = pd.to_datetime(df_for_forecast["ds"]) # Ensure 'ds' is datetime

        # Check if there are enough data points for Prophet
        if len(df_for_forecast) >= 2:
            try:
                # Create and fit the model
                model = Prophet()
                # Add seasonality if data duration is sufficient
                if (df_for_forecast['ds'].max() - df_for_forecast['ds'].min()).days >= 365 * 2: # At least 2 years for yearly
                    model.add_seasonality(name='yearly', period=365.25, fourier_order=10)
                if (df_for_forecast['ds'].max() - df_for_forecast['ds'].min()).days >= 7 * 2: # At least 2 weeks for weekly
                    model.add_seasonality(name='weekly', period=7, fourier_order=3)


                model.fit(df_for_forecast)

                # Create future dates for forecasting
                future = model.make_future_dataframe(periods=forecast_periods)  # Use selected periods
                forecast = model.predict(future)

                # Plot the forecast
                fig_forecast = model.plot(forecast)
                st.write(fig_forecast)

                # --- Display Insights ---
                st.subheader(f"💡 Insights dari Forecasting {forecast_type}")
                insights = generate_forecasting_insights(forecast, forecast_periods, data_type_label)
                for i, insight in enumerate(insights):
                    st.markdown(f"- {insight}")
                # --- End Display Insights ---

            except Exception as e:
                st.error(f"Terjadi kesalahan saat melakukan *forecasting* untuk {forecast_type}: {e}. Pastikan data Anda cukup bervariasi dan tidak kosong.")
        else:
            st.info(f"Tidak ada cukup data {forecast_type.lower()} (minimal 2 data poin) untuk melakukan *forecasting*.")
    # --- End Forecasting Section ---


def riwayat_page():
    st.title("📜 Riwayat Input Keuangan")
    username = st.session_state["username"]
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM laporan_keuangan WHERE username = ?", conn, params=(username,))
    conn.close()

    if df.empty:
        st.warning("Belum ada data.")
        return

    df["tanggal"] = pd.to_datetime(df["tanggal"]).dt.date

    for index, row in df.iterrows():
        with st.expander(f"{row['tanggal']} - {row['kategori']} - Rp{row['jumlah']:,.0f}".replace(",", ".")):
            st.write(f"*Jenis:* {row['jenis'].capitalize()}")
            st.write(f"*Jumlah:* Rp {row['jumlah']:,.0f}".replace(",", "."))
            st.write(f"*Dana Darurat:* Rp {row['dana_darurat']:,.0f}".replace(",", "."))
            st.write(f"*Keterangan:* {row['keterangan']}")
            if row['bukti_img']:
                st.image(row['bukti_img'], width=200)

            col1, col2 = st.columns(2)
            if col1.button("📝 Edit", key=f"edit_{row['id']}"):
                with st.form(f"form_edit_{row['id']}"):
                    new_tanggal = st.date_input("Tanggal", value=row['tanggal'], key=f"tgl_{row['id']}")
                    new_jenis = st.selectbox("Jenis", ["Pendapatan", "Pengeluaran"], index=0 if row['jenis'].lower() == "pendapatan" else 1, key=f"jenis_{row['id']}")
                    new_kategori = st.selectbox("Kategori",
                        ["Keuntungan"] if new_jenis == "Pendapatan" else ["Listrik", "Gaji", "PDAM", "Bahan Baku", "Sewa Tempat", "Lain-lain"],
                        index=0, key=f"kat_{row['id']}")
                    new_jumlah = st.number_input("Jumlah", value=row['jumlah'], step=1000, key=f"jml_{row['id']}")
                    new_keterangan = st.text_input("Keterangan", value=row['keterangan'], key=f"ket_{row['id']}")

                    submitted = st.form_submit_button("Simpan Perubahan")
                    if submitted:
                        username = st.session_state["username"] # Ensure username is available
                        emergency_rate, _ = get_user_settings(username) # Get current rate
                        new_dana_darurat = int(new_jumlah * (emergency_rate / 100)) if new_jenis == "Pendapatan" else 0

                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE laporan_keuangan
                            SET tanggal = ?, kategori = ?, jenis = ?, jumlah = ?, dana_darurat = ?, keterangan = ?
                            WHERE id = ? AND username = ?
                        """, (new_tanggal.isoformat(), new_kategori, new_jenis, new_jumlah, new_dana_darurat, new_keterangan, row['id'], username))
                        conn.commit()
                        conn.close()
                        st.success("✅ Data berhasil diperbarui.")
                        st.rerun()

            if col2.button("🗑️ Hapus", key=f"hapus_{row['id']}"):
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM laporan_keuangan WHERE id = ? AND username = ?", (row['id'], username))
                conn.commit()
                conn.close()
                st.success("✅ Data berhasil dihapus.")
                st.rerun()

def akun_page():
    st.markdown("<h1 style='text-align: center;'>👤 Akun Saya</h1>", unsafe_allow_html=True)
    username = st.session_state["username"]
    _, profile_pic = get_user_settings(username) # Only need profile_pic here now
    if profile_pic:
        encoded = base64.b64encode(profile_pic).decode()
        st.markdown(
            f"""
            <div style='text-align: center;'>
                <img src="data:image/png;base64,{encoded}" style="width: 200px; height: 200px; object-fit: cover; border-radius: 50%;">
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Belum ada foto profil.")
    uploaded_pic = st.file_uploader("Upload Foto Profil (opsional)", type=["jpg", "jpeg", "png"])
    if uploaded_pic:
        img = uploaded_pic.read()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET profile_pic = ? WHERE username = ?", (img, username))
        conn.commit()
        conn.close()
        st.success("✅ Foto profil berhasil diperbarui.")
        st.rerun()
    # Removed "Pengaturan Dana Darurat" from here

# New function for the minimalist login/register layout
def login_register_page():
    # Stylish CSS background with green gradient and cleaner layout
    st.markdown("""
        <style>
        .stApp {
            background: linear-gradient(135deg, #e8f5e9, #ffffff);
            color: #333;
            font-family: 'Segoe UI', sans-serif;
        }

       

        .app-title {
            font-size: 44px;
            text-align: center;
            color: #4CAF50;
            margin-bottom: 1.2rem;
            font-weight: 700;
        }

        .stTextInput > div > div > input {
            padding: 12px 14px;
            border-radius: 8px;
            border: 1px solid #d0d0d0;
            font-size: 16px;
        }

        .stTextInput > div > div > input:focus {
            border-color: #4CAF50;
            outline: none;
            box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.3);
        }

        .stButton > button {
            background-color: #4CAF50;
            color: white;
            font-weight: 600;
            font-size: 16px;
            padding: 0.75rem 1rem;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            width: 100%;
        }

        .stButton > button:hover {
            background-color: #43a047;
        }

        .stTabs [role="tablist"] {
            justify-content: center;
            margin-bottom: 1.5rem;
        }

        .stAlert {
            border-radius: 8px;
        }

        .stSidebar {
            display: none;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="card-login">', unsafe_allow_html=True)
    st.markdown('<div class="app-title">Xpense</div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🔐 Masuk", "📝 Daftar Akun"])

    with tab1:
        st.write("### Selamat Datang Kembali 👋")
        username = st.text_input("Username", key="login_username", placeholder="Masukkan username Anda")
        password = st.text_input("Password", type="password", key="login_password", placeholder="Masukkan password Anda")
        if st.button("Masuk", key="login_button"):
            if not username or not password:
                st.error("Username dan Password tidak boleh kosong.")
            else:
                success, role = login_user(username, password)
                if success:
                    st.success(f"Selamat datang, {username}!")
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username
                    st.session_state["role"] = role
                    st.rerun()
                else:
                    st.error("Username atau password salah.")

    with tab2:
        st.write("### Buat Akun Baru 🚀")
        new_username = st.text_input("Buat Username", key="register_username", placeholder="Contoh: johndoe")
        new_password = st.text_input("Buat Password", type="password", key="register_password", placeholder="Minimal 6 karakter")
        confirm_password = st.text_input("Konfirmasi Password", type="password", key="confirm_password", placeholder="Ketik ulang password")
        if st.button("Daftar", key="register_button"):
            if not new_username or not new_password or not confirm_password:
                st.error("Semua kolom harus diisi.")
            elif new_password != confirm_password:
                st.error("Password tidak cocok.")
            else:
                role = "user"
                if register_user(new_username, new_password, role):
                    st.success("🎉 Registrasi berhasil! Silakan login.")
                else:
                    st.error("Username sudah digunakan.")

    st.markdown('</div>', unsafe_allow_html=True)




def main():
    initialize_db()
    st.set_page_config(
        page_title="Xpense",
        layout="wide",
        page_icon="Xpense V5.png"  # nama file gambar
    )

    # Custom CSS to make sidebar buttons the same size
    st.markdown("""
        <style>
        .stButton > button {
            width: 100%; /* Make buttons take full width of their container */
            display: block; /* Ensure buttons are block level elements */
            margin-bottom: 5px; /* Add some space between buttons */
        }
        .sidebar-button-container .stButton > button {
            width: 150px; /* Adjust this value as needed for your desired fixed width */
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)


    if st.session_state.get("logged_in"):
        
        
        # Initialize session state for current_page if not set
        if "current_page" not in st.session_state:
            st.session_state["current_page"] = "Home" # Default page

        # Wrap each button in a div with a custom class to apply consistent width
        st.sidebar.markdown('<div class="sidebar-button-container">', unsafe_allow_html=True)
        if st.sidebar.button("🏠 Home"):
            st.session_state["current_page"] = "Home"
        if st.sidebar.button("📊 Dashboard"):
            st.session_state["current_page"] = "Dashboard"
        if st.sidebar.button("📜 Riwayat"):
            st.session_state["current_page"] = "Riwayat"
        if st.sidebar.button("👤 Akun"):
            st.session_state["current_page"] = "Akun"
        if st.sidebar.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()
        st.sidebar.markdown('</div>', unsafe_allow_html=True) # Close the container

        # Render the current page based on session state
        if st.session_state["current_page"] == "Home":
            home_page()
        elif st.session_state["current_page"] == "Dashboard":
            dashboard_page()
        elif st.session_state["current_page"] == "Riwayat":
            riwayat_page()
        elif st.session_state["current_page"] == "Akun":
            akun_page()
            
    else:
        login_register_page() # Call the new login/register page function

if __name__ == "__main__":
    main()