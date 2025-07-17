import streamlit as st
import pandas as pd
import requests
import io
import altair as alt
import base64

# ————————————————
# Inyectar logos en esquinas
# ————————————————

def _get_base64(bin_file):
    with open(bin_file, 'rb') as f:
        return base64.b64encode(f.read()).decode()

logo_top = _get_base64('Recurso 1.png')       # "Potencia Digital"
logo_bottom = _get_base64('symbol.png')       # Símbolo

# ————————————————
# Funciones comunes
# ————————————————

def format_cop(x):
    try:
        val = float(x)
    except Exception:
        return "" if pd.isna(x) else x
    return f"${val:,.0f}"

@st.cache_data(ttl=600)
def cargar_tablas_control():
    xls = pd.ExcelFile("Tablas Control.xlsx")
    df_mun = pd.read_excel(xls, sheet_name="Tablamun")
    df_dep = pd.read_excel(xls, sheet_name="Tabladep")
    df_per = (
        pd.read_excel(xls, sheet_name="Periodos")
          .rename(columns={"Personalizado.1": "periodo_label"})
    )
    return df_mun, df_dep, df_per

@st.cache_data(ttl=600, show_spinner=False)
def obtener_ingresos(codigo_entidad, periodo=None):
    url = "https://www.datos.gov.co/resource/22ah-ddsj.json"
    where = f"codigo_entidad='{codigo_entidad}'"
    if periodo:
        where += f" AND periodo='{periodo}'"
    params = {"$where": where, "$limit": 50000}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    for col in ['valor', 'presupuesto_inicial', 'presupuesto_definitivo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    return df

@st.cache_data(ttl=600, show_spinner=False)
def obtener_datos_gastos(codigo_entidad, periodo):
    cols = [
        "periodo", "codigo_entidad", "nombre_entidad",
        "cuenta", "nombre_cuenta", "compromisos", "pagos", "obligaciones", "nom_vigencia_del_gasto"
    ]
    where = (
        f"codigo_entidad='{codigo_entidad}' AND "
        f"periodo='{periodo}'"
    )
    params = {"$select": ",".join(cols), "$where": where, "$limit": 10000}
    r = requests.get("https://www.datos.gov.co/resource/4f7r-epif.csv", params=params, timeout=30)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))

@st.cache_data(ttl=300)
def fetch_account_data(periodo: str, ambito_code: str) -> pd.DataFrame:
    """
    Obtiene registros de la API 22ah-ddsj filtrando por periodo y ambito_codigo,
    y corrige el bug renombrando las columnas de detalle_sectorial.
    """
    url = "https://www.datos.gov.co/resource/22ah-ddsj.json"
    params = {
        "$where": f"periodo='{periodo}' AND ambito_codigo='{ambito_code}'",
        "$limit": 50000
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())

    # La API trae los montos en:
    #  - cod_detalle_sectorial  → presupuesto_inicial
    #  - nom_detalle_sectorial  → presupuesto_definitivo
    if 'cod_detalle_sectorial' in df.columns:
        df['presupuesto_inicial'] = pd.to_numeric(
            df['cod_detalle_sectorial'].astype(str).str.replace(',', ''),
            errors='coerce'
        )
    if 'nom_detalle_sectorial' in df.columns:
        df['presupuesto_definitivo'] = pd.to_numeric(
            df['nom_detalle_sectorial'].astype(str).str.replace(',', ''),
            errors='coerce'
        )
    return df

# ————————————————
# Carga de tablas de control
# ————————————————
df_mun, df_dep, df_per = cargar_tablas_control()
# Carga adicional de cuentas de ingresos
df_cuentas_control = pd.read_excel("Tablas Control.xlsx", sheet_name="Tablacontrolingresos")

# ————————————————
# Configuración de la página
# ————————————————
st.set_page_config(page_title="Análisis Financiero", layout="wide")

# ————————————————
# Navegación de páginas
# ————————————————
pagina = st.sidebar.selectbox("Selecciona página:", [
    "Programación de Ingresos", "Ejecución de Gastos", "Comparativa de Ingresos"
])

# Logos en sidebar
st.sidebar.markdown(
    f"""
    <style>
      .sidebar-logo {{
        position: absolute;
        bottom: 100px;
        left: 0;
        right: 0;
        text-align: center;
        z-index: 1000;
        pointer-events: none;
      }}
      .sidebar-logo img {{
        width: 150px;
      }}
      .sidebar-logo2 {{
        position: absolute;
        bottom: -575px;
        left: 50%;
        transform: translateX(-50%);
        width: 100px;
        z-index: 1000;
      }}
    </style>
    <div class="sidebar-logo">
      <img src="data:image/png;base64,{logo_top}" alt="Potencia Digital" />
    </div>
    <div class="sidebar-logo2">
      <img src="data:image/png;base64,{logo_bottom}" alt="Symbol" />
    </div>
    """,
    unsafe_allow_html=True
)

# ————————————————
# Páginas
# ————————————————
if pagina == "Programación de Ingresos":
    st.title("💰 Programación de Ingresos")

    # 1) Selección geográfica
    nivel = st.selectbox("Nivel geográfico:", ["Municipios", "Gobernaciones"])
    if nivel == "Municipios":
        raw_deps = df_mun["departamento"].dropna().unique()
        deps = sorted(str(d) for d in raw_deps)
        dep = st.selectbox("Departamento:", deps)
        df_ent = df_mun[df_mun["departamento"].astype(str) == dep]
        label = "Municipio"
    else:
        df_ent = df_dep
        label = "Gobernación"
    ent = st.selectbox(f"Selecciona {label}:", df_ent["nombre_entidad"].dropna().astype(str).tolist())
    cod_ent = str(df_ent.loc[df_ent["nombre_entidad"] == ent, "codigo_entidad"].iloc[0])

    # 2) Selección de período
    per_lab = st.selectbox("Período puntual:", df_per["periodo_label"].tolist())
    per     = str(df_per.loc[df_per["periodo_label"] == per_lab, "periodo"].iloc[0])

    # 3) Carga de datos
    if st.button("Cargar ingresos"):
        with st.spinner("Cargando datos..."):
            df_raw = obtener_ingresos(cod_ent, per)

            # **Mapeo del bug de la API**:  
            # Si existen columnas de detalle sectorial, las convertimos a presupuestos
            if 'cod_detalle_sectorial' in df_raw.columns:
                df_raw['presupuesto_inicial'] = pd.to_numeric(
                    df_raw['cod_detalle_sectorial'].astype(str).str.replace(',', ''),
                    errors='coerce'
                )
            if 'nom_detalle_sectorial' in df_raw.columns:
                df_raw['presupuesto_definitivo'] = pd.to_numeric(
                    df_raw['nom_detalle_sectorial'].astype(str).str.replace(',', ''),
                    errors='coerce'
                )

            st.session_state["df_ingresos"] = df_raw

    # 4) Si ya cargamos…
    if "df_ingresos" in st.session_state:
        df_i = st.session_state["df_ingresos"]
        st.subheader("1. Datos brutos de ingresos")
        st.dataframe(df_i, use_container_width=True)

        #  descarga Excel…
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as wr:
            df_i.to_excel(wr, index=False, sheet_name="Brutos")
        buf.seek(0)
        st.download_button("⬇️ Descargar brutos", buf,
                           "datos_brutos.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # 5) Filtrar ámbitos (guarda si no existe ambito_codigo)
        codigos = ["1","1.1","1.1.01.01.200","1.1.01.02.104","1.1.01.02.200",
                   "1.1.01.02.300","1.1.02.06.001","1.2.06","1.2.07"]
        if 'ambito_codigo' in df_i.columns:
            mask = df_i['ambito_codigo'].fillna('').astype(str).isin(codigos)
        else:
            mask = pd.Series([False]*len(df_i))
        df_fil = df_i[mask]

        # 6) Convertir a millones
        if 'presupuesto_inicial' in df_fil.columns:
            df_fil['presupuesto_inicial']   /= 1e6
        if 'presupuesto_definitivo' in df_fil.columns:
            df_fil['presupuesto_definitivo'] /= 1e6

        # 7) Renombrado dinámico SOLO de las columnas existentes
        rename_map = {
            'periodo':                'Periodo',
            'codigo_entidad':         'Código Entidad',
            'nombre_entidad':         'Nombre Entidad',
            'ambito_codigo':          'Ámbito Código',
            'ambito_nombre':          'Ámbito Nombre',
            'nombre_cuenta':          'Nombre Cuenta',
            'presupuesto_inicial':    'Presupuesto Inicial',
            'presupuesto_definitivo': 'Presupuesto Definitivo'
        }
        # Filtrar el map solo a las keys presentes
        actual_keys = [k for k in rename_map if k in df_fil.columns]
        resumen = (
            df_fil
            .rename(columns={k: rename_map[k] for k in actual_keys})
            [[rename_map[k] for k in actual_keys]]
            .reset_index(drop=True)
        )

        # 8) Formatear COP
        for col in ('Presupuesto Inicial', 'Presupuesto Definitivo'):
            if col in resumen.columns:
                resumen[col] = resumen[col].map(format_cop)

        # 9) Total definitivo (ya en millones)
        total = df_fil['presupuesto_definitivo'].sum() if 'presupuesto_definitivo' in df_fil.columns else 0.0

        # 10) Mostrar
        st.subheader("2. Resumen de ingresos filtrados (millones de pesos)")
        st.markdown(resumen.to_html(index=False, escape=False), unsafe_allow_html=True)

        st.subheader("3. Total Presupuesto Definitivo (INGRESOS) (millones de pesos)")
        st.metric("", format_cop(total * 1e6))

    # 3) Histórico Nominal vs Real con escala ajustada al mínimo real
    if st.button("Mostrar histórico"):
        with st.spinner("Obteniendo histórico Q4..."):
            df_hist = obtener_ingresos(cod_ent)
            df_hist.columns = df_hist.columns.str.strip()
            df_hist = df_hist[df_hist['ambito_nombre'].str.upper() == 'INGRESOS']
            df_hist['periodo_dt'] = pd.to_datetime(df_hist['periodo'], format='%Y%m%d', errors='coerce')
            df_hist['year']      = df_hist['periodo_dt'].dt.year
            df_hist['md']        = df_hist['periodo_dt'].dt.strftime('%m%d')

            registros = []
            current = df_hist['year'].max()
            for yr, grp in df_hist.groupby('year'):
                if yr != current:
                    q4 = grp[grp['md']=='1201']
                    if not q4.empty:
                        registros.append(q4.loc[q4['periodo_dt'].idxmax()])
                else:
                    registros.append(grp.loc[grp['periodo_dt'].idxmax()])

            df_sel = pd.DataFrame(registros).sort_values('periodo_dt')
            df_sel.columns = df_sel.columns.str.strip()

            if 'nom_detalle_sectorial' not in df_sel:
                st.error("No se encontró la columna 'nom_detalle_sectorial' en los datos históricos.")
            else:
                # Ingresos nominales en millones
                df_sel['Ingresos Nominales'] = pd.to_numeric(df_sel['nom_detalle_sectorial'], errors='coerce') / 1e6

                # IPC y serie real
                ipc_map = {2021:111.41, 2022:126.03, 2023:137.09, 2024:144.88}
                df_chart = df_sel.set_index('periodo_dt').reset_index().rename(columns={'periodo_dt':'Periodo'})
                df_chart['Año'] = df_chart['Periodo'].dt.year
                df_chart['ipc_base2018'] = df_chart['Año'].map(ipc_map)
                df_chart['Ingresos Reales'] = df_chart['Ingresos Nominales'] / df_chart['ipc_base2018'] * 100

                # Convertir a formato largo
                df_long = df_chart.melt(
                    id_vars=['Periodo'],
                    value_vars=['Ingresos Nominales','Ingresos Reales'],
                    var_name='Tipo de ingreso',
                    value_name='Monto'
                )

                # Dominio Y: mínimo de reales y máximo global
                min_real = df_chart['Ingresos Reales'].min()
                max_all  = df_long['Monto'].max()
                dominio  = [min_real * 0.9, max_all * 1.02]

                # Gráfico con leyenda y colores distintos
                chart = alt.Chart(df_long).mark_line(point=True).encode(
                    x=alt.X('Periodo:T', title='Periodo', axis=alt.Axis(format='%Y', tickCount='year')),
                    y=alt.Y('Monto:Q',
                            title='Ingresos Q4 (millones de pesos)',
                            axis=alt.Axis(format='$,.0f'),
                            scale=alt.Scale(domain=dominio, nice=False)),
                    color=alt.Color('Tipo de ingreso:N', title='Serie',
                                    scale=alt.Scale(range=['#1f77b4','#ff7f0e'])),
                    tooltip=[
                        alt.Tooltip('Periodo:T', title='Periodo'),
                        alt.Tooltip('Tipo de ingreso:N', title='Tipo'),
                        alt.Tooltip('Monto:Q', title='Monto', format='$,.0f')
                    ]
                ).properties(width=600, height=300)

                st.subheader("4. Histórico de INGRESOS Nominales vs Reales (Q4) (millones de pesos)")
                st.altair_chart(chart, use_container_width=True)

                # Descargar todas las tablas
                buf_all = io.BytesIO()
                with pd.ExcelWriter(buf_all, engine="openpyxl") as writer:
                    st.session_state["df_ingresos"].to_excel(writer, index=False, sheet_name="Datos Brutos")
                    resumen.to_excel(writer, index=False, sheet_name="Resumen")
                    df_chart[['Periodo','Ingresos Nominales','Ingresos Reales']].to_excel(
                        writer, index=False, sheet_name="Histórico Q4"
                    )
                buf_all.seek(0)
                st.download_button(
                    "⬇️ Descargar todas las tablas en Excel",
                    data=buf_all,
                    file_name="ingresos_completo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

elif pagina == "Ejecución de Gastos":
    st.title("💸 Ejecución de Gastos")

    nivel = st.selectbox("Selecciona el nivel", ["Municipios", "Gobernaciones"])
    if nivel == "Municipios":
        raw_deps = df_mun["departamento"].dropna().unique()
        deps = sorted(str(d) for d in raw_deps)
        dep_sel = st.selectbox("Selecciona el departamento", deps)
        df_entidades = df_mun[df_mun["departamento"].astype(str) == dep_sel]
        label_ent = "Selecciona el municipio"
    else:
        df_entidades = df_dep
        label_ent = "Selecciona la gobernación"
    ent_sel = st.selectbox(label_ent, df_entidades["nombre_entidad"].dropna().astype(str).tolist())
    codigo_ent = str(df_entidades.loc[df_entidades["nombre_entidad"] == ent_sel, "codigo_entidad"].iloc[0])
    periodo_label_g = st.selectbox("Selecciona el periodo", df_per["periodo_label"].tolist())
    periodo = str(df_per.loc[df_per["periodo_label"] == periodo_label_g, "periodo"].iloc[0])

   # Cargar datos
    if st.button("Cargar datos"):
        st.session_state["df_gastos"] = obtener_datos_gastos(codigo_ent, periodo)

    if "df_gastos" in st.session_state:
        df_raw = st.session_state["df_gastos"]

        # ===== DATOS BRUTOS =====
        st.write("### Datos brutos")
        st.dataframe(
            df_raw.style.format({
                "compromisos": format_cop,
                "pagos": format_cop,
                "obligaciones": format_cop
            }), use_container_width=True
        )
        # Descargar Datos brutos
        buf_raw = io.BytesIO()
        with pd.ExcelWriter(buf_raw) as writer:
            df_raw.to_excel(writer, sheet_name='DatosBrutos', index=False)
        st.download_button(
            label='Descargar Datos Brutos (Excel)',
            data=buf_raw.getvalue(),
            file_name='datos_brutos.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        # Filtrar solo VIGENCIA ACTUAL y cuentas relevantes
        cuentas_filtro = [
            "2", "2.1.1", "2.1.2.01.01.001", "2.1.2.01.01.003", "2.1.2.01.01.004",
            "2.1.2.01.01.005", "2.1.2.01.02", "2.1.2.01.03", "2.1.2.02.01",
            "2.1.2.02.02", "2.1.3.01", "2.1.3.02.01", "2.1.3.02.02", "2.1.3.02.03",
            "2.1.3.02.04", "2.1.3.02.05", "2.1.3.02.06", "2.1.3.02.07", "2.1.3.02.08",
            "2.1.3.02.09", "2.1.3.02.10", "2.1.3.02.11", "2.1.3.02.12", "2.1.3.02.13",
            "2.1.3.02.14", "2.1.3.02.15", "2.1.3.02.16", "2.1.3.02.17", "2.1.3.02.18",
            "2.1.3.03", "2.1.3.04", "2.1.3.05.01", "2.1.3.05.04", "2.1.3.05.07",
            "2.1.3.05.08", "2.1.3.05.09", "2.1.3.06", "2.1.3.07.02", "2.1.3.07.03",
            "2.1.3.08", "2.1.3.09", "2.1.3.10", "2.1.3.11.02", "2.1.3.11.03",
            "2.1.3.12", "2.1.3.13", "2.1.3.14", "2.1.4.02", "2.1.4.03", "2.1.4.04",
            "2.1.4.07", "2.1.5.01", "2.1.5.02", "2.1.6.01", "2.1.6.02", "2.1.6.03",
            "2.1.7.01", "2.1.7.02", "2.1.7.03", "2.1.7.04", "2.1.7.05", "2.1.7.06",
            "2.1.7.09", "2.1.8", "2.2.1", "2.2.2", "2.3.1", "2.3.2.01.01.001",
            "2.3.2.01.01.003", "2.3.2.01.01.004", "2.3.2.01.01.005", "2.3.2.01.02",
            "2.3.2.01.03", "2.3.2.02.01", "2.3.2.02.02", "2.3.3.01.02", "2.3.3.01.04",
            "2.3.3.02.01", "2.3.3.02.02", "2.3.3.02.03", "2.3.3.02.04", "2.3.3.02.05",
            "2.3.3.02.06", "2.3.3.02.07", "2.3.3.02.08", "2.3.3.02.09", "2.3.3.02.10",
            "2.3.3.02.11", "2.3.3.02.12", "2.3.3.02.13", "2.3.3.02.14", "2.3.3.02.15",
            "2.3.3.02.16", "2.3.3.02.17", "2.3.3.02.18", "2.3.3.03", "2.3.3.04",
            "2.3.3.05", "2.3.3.06", "2.3.3.07.01", "2.3.3.07.02", "2.3.3.08",
            "2.3.3.09", "2.3.3.11", "2.3.3.12", "2.3.3.13", "2.3.3.14", "2.3.4.01",
            "2.3.4.02", "2.3.4.03", "2.3.4.04", "2.3.4.07", "2.3.4.09", "2.3.5.01",
            "2.3.5.02", "2.3.6.01", "2.3.6.02", "2.3.6.03", "2.3.7.01", "2.3.7.05",
            "2.3.7.06", "2.3.8"
        ]
        df_filtered = df_raw[
            df_raw["cuenta"].isin(cuentas_filtro) &
            df_raw["nom_vigencia_del_gasto"].str.strip().str.upper().eq("VIGENCIA ACTUAL")
        ]

        # ===== RESUMEN =====
        resumen = (
            df_filtered
            .groupby(["cuenta", "nombre_cuenta"], as_index=False)[["compromisos", "pagos", "obligaciones"]]
            .sum()
        )
        resumen = resumen[resumen["nombre_cuenta"].str.upper() != "GASTOS"]
        tot = resumen[["compromisos", "pagos", "obligaciones"]].sum()
        resumen = pd.concat([resumen, pd.DataFrame([{"cuenta":"","nombre_cuenta":"TOTAL", **tot.to_dict()}])], ignore_index=True)

        resumen_disp = resumen.rename(columns={
            'cuenta': 'Cuenta',
            'nombre_cuenta': 'Nombre cuenta',
            'compromisos': 'Compromisos',
            'pagos': 'Pagos',
            'obligaciones': 'Obligaciones'
        })
        resumen_disp[['Compromisos','Pagos','Obligaciones']] = resumen_disp[['Compromisos','Pagos','Obligaciones']] / 1_000_000
        resumen_disp[['Compromisos','Pagos','Obligaciones']] = resumen_disp[['Compromisos','Pagos','Obligaciones']].applymap(format_cop)
        st.write("### Resumen de compromisos, pagos y obligaciones por cuenta (en millones de pesos)")
        st.markdown(resumen_disp.to_html(index=False), unsafe_allow_html=True)

        # ===== DETALLE GASTOS =====
        gastos = (
            df_filtered[df_filtered["nombre_cuenta"].str.upper() == "GASTOS"]
            .groupby(["cuenta", "nombre_cuenta"], as_index=False)[["compromisos", "pagos", "obligaciones"]]
            .sum()
        )
        gastos_disp = gastos.drop(columns=["cuenta", "nombre_cuenta"]).rename(columns={
            'compromisos': 'Compromisos',
            'pagos': 'Pagos',
            'obligaciones': 'Obligaciones'
        })
        gastos_disp[['Compromisos','Pagos','Obligaciones']] = gastos_disp[['Compromisos','Pagos','Obligaciones']] / 1_000_000
        gastos_disp[['Compromisos','Pagos','Obligaciones']] = gastos_disp[['Compromisos','Pagos','Obligaciones']].applymap(format_cop)
        st.write("### Detalle GASTOS (en millones de pesos)")
        st.markdown(gastos_disp.to_html(index=False), unsafe_allow_html=True)

        # ===== CONSOLIDADO =====
        vigencias = ["VIGENCIA ACTUAL","RESERVAS","VIGENCIAS FUTURAS - RESERVAS","CUENTAS POR PAGAR","VIGENCIAS FUTURAS - VIGENCIA ACTUAL"]
        df_consol = df_raw[
            df_raw["nom_vigencia_del_gasto"].str.strip().str.upper().isin(vigencias) &
            df_raw["nombre_cuenta"].str.strip().str.upper().eq("GASTOS")
        ]
        consolidado = df_consol.groupby("nom_vigencia_del_gasto", as_index=False)[["compromisos","pagos","obligaciones"]].sum()
        tot_con = consolidado[["compromisos","pagos","obligaciones"]].sum()
        consolidado = pd.concat([consolidado, pd.DataFrame([{"nom_vigencia_del_gasto":"TOTAL", **tot_con.to_dict()}])], ignore_index=True)

        consolidado_disp = consolidado.rename(columns={
            'nom_vigencia_del_gasto': 'Vigencia del gasto',
            'compromisos': 'Compromisos',
            'pagos': 'Pagos',
            'obligaciones': 'Obligaciones'
        })
        consolidado_disp[['Compromisos','Pagos','Obligaciones']] = consolidado_disp[['Compromisos','Pagos','Obligaciones']] / 1_000_000
        consolidado_disp[['Compromisos','Pagos','Obligaciones']] = consolidado_disp[['Compromisos','Pagos','Obligaciones']].applymap(format_cop)
        st.write("### Consolidado de GASTOS por tipo de vigencia (en millones de pesos)")
        st.markdown(consolidado_disp.to_html(index=False), unsafe_allow_html=True)

        # Métrica total global
        st.metric("Total compromisos para todas las vigencias", format_cop(tot_con["compromisos"]/1_000_000))

        # Botón descargar todo debajo de la métrica
        buf_all = io.BytesIO()
        with pd.ExcelWriter(buf_all) as writer:
            df_raw.to_excel(writer, sheet_name='DatosBrutos', index=False)
            resumen_disp.to_excel(writer, sheet_name='Resumen', index=False)
            gastos_disp.to_excel(writer, sheet_name='DetalleGastos', index=False)
            consolidado_disp.to_excel(writer, sheet_name='Consolidado', index=False)
        st.download_button(
            label='Descargar Todo (Excel)',
            data=buf_all.getvalue(),
            file_name='ejecucion_gastos_completo.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

elif pagina == "Comparativa de Ingresos":
    st.title("📊 Comparativa Per Cápita (Media Aritmética)")
    st.sidebar.header("Parámetros de consulta")
    raw_deps = df_mun['departamento'].dropna().unique()
    departamentos = sorted(str(d) for d in raw_deps)
    departamento = st.sidebar.selectbox("Departamento", departamentos)
    df_dep_comp = df_mun[df_mun['departamento'].astype(str) == departamento]
    municipio = st.sidebar.selectbox("Municipio", df_dep_comp['nombre_entidad'].dropna().astype(str).unique())
    periodo_label = st.sidebar.selectbox("Período (label)", df_per['periodo_label'].tolist())
    periodo = str(df_per.loc[df_per['periodo_label'] == periodo_label, 'periodo'].iloc[0])
    cuenta = st.sidebar.selectbox("Cuenta", df_cuentas_control['Nombre de la Cuenta'].dropna().astype(str).unique())
    ambito_code = str(df_cuentas_control.loc[df_cuentas_control['Nombre de la Cuenta'] == cuenta, 'Código Completo'].iloc[0])
    if st.sidebar.button("🚀 Ejecutar comparativa"):
        df_acct = fetch_account_data(periodo, ambito_code)
        if df_acct.empty:
            st.warning("No hay datos para esa cuenta y período.")
            st.stop()
        df_acct['presupuesto_def'] = df_acct['presupuesto_definitivo']
        df_sum = df_acct.groupby('nombre_entidad', as_index=False)['presupuesto_def'].sum()
        df_sum = df_sum.merge(df_mun[['nombre_entidad','poblacion','categoria']], on='nombre_entidad', how='left').dropna(subset=['poblacion'])
        df_sum['per_capita'] = df_sum['presupuesto_def'] / df_sum['poblacion']
        sel = df_sum[df_sum['nombre_entidad'] == municipio]
        pc_sel = sel['per_capita'].iloc[0] if not sel.empty else 0.0
        abs_sel = sel['presupuesto_def'].iloc[0] if not sel.empty else 0.0
        cat = sel['categoria'].iloc[0] if not sel.empty else None
        pc_cat = df_sum[df_sum['categoria'] == cat]['per_capita'].mean() if cat else 0.0
        abs_cat = df_sum[df_sum['categoria'] == cat]['presupuesto_def'].mean() if cat else 0.0
        pc_all = df_sum['per_capita'].mean()
        abs_all = df_sum['presupuesto_def'].mean()
        df_bar = pd.DataFrame({'Tipo':[municipio,f'Promedio Cat. ({cat})','Promedio País'], 'COP per cápita':[pc_sel,pc_cat,pc_all],'Absoluto':[abs_sel,abs_cat,abs_all]})
        df_bar['COP per cápita']=df_bar['COP per cápita'].apply(format_cop)
        df_bar['Absoluto']=df_bar['Absoluto'].apply(format_cop)
        df_plot=pd.DataFrame({'Tipo':df_bar['Tipo'],'Value':[pc_sel,pc_cat,pc_all]})
        chart=alt.Chart(df_plot).mark_bar(cornerRadius=4).encode(
            x=alt.X('Tipo:N',title='',axis=alt.Axis(labelAngle=0)),
            y=alt.Y('Value:Q',title='COP per cápita',axis=alt.Axis(format='$,.0f')),
            color=alt.condition(alt.datum.Tipo==municipio,alt.value('orange'),alt.value('steelblue')),
            tooltip=[alt.Tooltip('Tipo:N',title='Tipo'),alt.Tooltip('Value:Q',title='COP per cápita',format='$,.0f')]
        ).properties(title=f"Comparativa Per Cápita: {municipio}",width=600,height=400)
        st.altair_chart(chart,use_container_width=True)
        st.subheader('📋 Valores per cápita y absolutos')
        st.table(df_bar.set_index('Tipo'))
        st.subheader(f'🏘️ Detalle por municipio (Categoría: {cat})')
        df_cat=df_sum[df_sum['categoria']==cat].copy().rename(columns={'nombre_entidad':'Municipio','presupuesto_def':'Absoluto','per_capita':'COP per cápita'})
        df_cat=df_cat.sort_values('Absoluto',ascending=False)
        df_cat['Absoluto']=df_cat['Absoluto'].apply(format_cop)
        df_cat['COP per cápita']=df_cat['COP per cápita'].apply(format_cop)
        styled=df_cat.set_index('Municipio').style.apply(lambda row:['color: orange' if row.name==municipio else '' for _ in row],axis=1)
        st.dataframe(styled)

















