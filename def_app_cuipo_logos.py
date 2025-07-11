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
logo_bottom = _get_base64('symbol.png')  # Símbolo

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

# ————————————————
# Carga de tablas de control
# ————————————————
df_mun, df_dep, df_per = cargar_tablas_control()

# ————————————————
# Configuración de la página
# ————————————————
st.set_page_config(page_title="Análisis Financiero", layout="wide")

# ————————————————
# Navegación de páginas
# ————————————————
pagina = st.sidebar.selectbox("Selecciona página:", [
    "Programación de Ingresos", "Ejecución de Gastos"
])
# Ahora, coloca el logo al pie del sidebar
st.sidebar.markdown(
    f"""
    <style>
      /* Contenedor absoluto al pie del sidebar */
      .sidebar-logo {{
        position: absolute;
        bottom: 100px;       /* ← ESTA LÍNEA determina la distancia desde el borde inferior */
        left: 0;
        right: 0;
        text-align: center;
        z-index: 1000;
        pointer-events: none;
      }}
      /* Ajusta el tamaño del logo */
      .sidebar-logo img {{
        width: 150px;
      }}
      .sidebar-logo2 {{
        position: absolute;
        bottom: -575px;      /* ← ESTA LÍNEA determina la altura del segundo logo */
        left: 50%;
        transform: translateX(-50%);
        width: 100px;      /* ajusta al tamaño que quieras */
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

if pagina == "Programación de Ingresos":
    st.title("💰 Programación de Ingresos")

    # Selección de nivel geográfico
    nivel = st.selectbox("Nivel geográfico:", ["Municipios", "Gobernaciones"])
    if nivel == "Municipios":
        deps = sorted(df_mun["departamento"].unique())
        dep = st.selectbox("Departamento:", deps)
        df_ent = df_mun[df_mun["departamento"] == dep]
        label = "Municipio"
    else:
        df_ent = df_dep
        label = "Gobernación"
    ent = st.selectbox(f"Selecciona {label}:", df_ent["nombre_entidad"].tolist())
    cod_ent = str(df_ent.loc[df_ent["nombre_entidad"] == ent, "codigo_entidad"].iloc[0])

    # Selección de período
    per_lab = st.selectbox("Período puntual:", df_per["periodo_label"].tolist())
    per = str(df_per.loc[df_per["periodo_label"] == per_lab, "periodo"].iloc[0])

    if st.button("Cargar ingresos"):
        with st.spinner("Cargando datos..."):
            st.session_state["df_ingresos"] = obtener_ingresos(cod_ent, per)

    if "df_ingresos" in st.session_state:
        df_i = st.session_state["df_ingresos"]
        st.subheader("1. Datos brutos de ingresos")
        st.dataframe(df_i, use_container_width=True)

        codigos_ambito = [
            "1", "1.1", "1.1.01.01.200", "1.1.01.02.104",
            "1.1.01.02.200", "1.1.01.02.300", "1.1.02.06.001",
            "1.2.06", "1.2.07"
        ]
        df_filtrado = df_i[df_i.get("ambito_codigo", "").isin(codigos_ambito)]
        drop_cols = [c for c in ['cuenta', 'presupuesto_inicial', 'presupuesto_definitivo'] if c in df_filtrado.columns]
        resumen = df_filtrado.drop(columns=drop_cols)
        resumen = resumen.rename(columns={
            'cod_detalle_sectorial': 'Presupuesto Inicial',
            'nom_detalle_sectorial': 'Presupuesto Definitivo'
        })

        st.subheader("2. Resumen de ingresos filtrados")
        styled = resumen.style.format({
            "Presupuesto Inicial": format_cop,
            "Presupuesto Definitivo": format_cop
        })
        st.dataframe(styled, use_container_width=True)

        if 'ambito_nombre' in resumen.columns and 'Presupuesto Definitivo' in resumen.columns:
            total_ing = resumen.loc[resumen['ambito_nombre'].str.upper() == 'INGRESOS', 'Presupuesto Definitivo'].sum()
            st.subheader("3. Total Presupuesto Definitivo (INGRESOS)")
            st.metric("", format_cop(total_ing))

    if st.button("Mostrar histórico"):
        with st.spinner("Obteniendo histórico Q4..."):
            df_hist = obtener_ingresos(cod_ent)
            df_hist.columns = df_hist.columns.str.strip()
            df_hist = df_hist[df_hist.get('ambito_nombre', '').str.upper() == 'INGRESOS']
            df_hist['periodo_dt'] = pd.to_datetime(df_hist['periodo'], format='%Y%m%d', errors='coerce')
            df_hist['year'] = df_hist['periodo_dt'].dt.year
            df_hist['md'] = df_hist['periodo_dt'].dt.strftime('%m%d')
            current_year = df_hist['year'].max()
            registros = []
            for yr, grp in df_hist.groupby('year'):
                if yr != current_year:
                    q4 = grp[grp['md'] == '1201']
                    if not q4.empty:
                        registros.append(q4.loc[q4['periodo_dt'].idxmax()])
                else:
                    registros.append(grp.loc[grp['periodo_dt'].idxmax()])
            df_sel = pd.DataFrame(registros).sort_values('periodo_dt')
            df_sel.columns = df_sel.columns.str.strip()
            if 'nom_detalle_sectorial' in df_sel.columns:
                df_sel['nom_detalle_sectorial'] = pd.to_numeric(df_sel['nom_detalle_sectorial'], errors='coerce')
                df_sel = df_sel.set_index('periodo_dt')
                st.subheader("4. Histórico de INGRESOS (Q4)")
                df_chart = df_sel.reset_index()
                chart = alt.Chart(df_chart).mark_line(point=True).encode(
                     x=alt.X('periodo_dt:T', title='Periodo',
                            axis=alt.Axis(format='%Y',
                                          tickCount='year')),
                    y=alt.Y('nom_detalle_sectorial:Q', title='Ingresos Q4', axis=alt.Axis(format='$,.0f')),
                    tooltip=[
                        alt.Tooltip('periodo_dt:T', title='Periodo'),
                        alt.Tooltip('nom_detalle_sectorial:Q', title='Ingresos Q4', format='$,.0f')
                    ]
                ).properties(width=600, height=300)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.error("No se encontró la columna 'nom_detalle_sectorial' en los datos históricos.")

elif pagina == "Ejecución de Gastos":
    st.title("💸 Ejecución de Gastos")

    nivel = st.selectbox("Selecciona el nivel", ["Municipios", "Gobernaciones"])
    if nivel == "Municipios":
        departamentos = sorted(df_mun["departamento"].unique())
        dep_sel = st.selectbox("Selecciona el departamento", departamentos)
        df_entidades = df_mun[df_mun["departamento"] == dep_sel]
        label_ent = "Selecciona el municipio"
    else:
        df_entidades = df_dep
        label_ent = "Selecciona la gobernación"
    ent_sel = st.selectbox(label_ent, df_entidades["nombre_entidad"].tolist())
    codigo_ent = str(df_entidades.loc[df_entidades["nombre_entidad"] == ent_sel, "codigo_entidad"].iloc[0])

    periodo_label_g = st.selectbox("Selecciona el periodo", df_per["periodo_label"].tolist())
    periodo = str(df_per.loc[df_per["periodo_label"] == periodo_label_g, "periodo"].iloc[0])

    # Botón para cargar datos brutos
    if st.button("Cargar datos"):
        st.session_state["df_gastos"] = obtener_datos_gastos(codigo_ent, periodo)

    # Mostrar datos y resumen automáticamente
    if "df_gastos" in st.session_state:
        df_raw = st.session_state["df_gastos"]

        st.write("### Datos brutos")
        st.dataframe(
            df_raw.style.format({
                "compromisos": format_cop,
                "pagos": format_cop,
                "obligaciones": format_cop
            }), use_container_width=True
        )

        # Filtrar por lista de códigos y por VIGENCIA ACTUAL
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

        df_filtered = df_raw[
            df_raw["cuenta"].isin(cuentas_filtro) &
            df_raw["nom_vigencia_del_gasto"].str.strip().str.upper().eq("VIGENCIA ACTUAL")
        ]

        # Resumen general (sin index)
        resumen = df_filtered.groupby(["cuenta","nombre_cuenta"], as_index=False)[["compromisos","pagos","obligaciones"]].sum()
        resumen = resumen[resumen["nombre_cuenta"].str.upper() != "GASTOS"]
        tot = resumen[["compromisos","pagos","obligaciones"]].sum()
        resumen = pd.concat([resumen, pd.DataFrame([{"cuenta":"","nombre_cuenta":"TOTAL",**tot.to_dict()}])], ignore_index=True)
        # Formato y renderizado sin índice
        resumen_disp = resumen.copy()
        for col in ["compromisos","pagos","obligaciones"]:
            resumen_disp[col] = resumen_disp[col].apply(format_cop)
        st.write("### Resumen de compromisos, pagos y obligaciones por cuenta")
        st.markdown(resumen_disp.to_html(index=False), unsafe_allow_html=True)

        # Detalle GASTOS
        gastos = df_filtered[df_filtered["nombre_cuenta"].str.upper()=="GASTOS"]
        gastos = gastos.groupby(["cuenta","nombre_cuenta"], as_index=False)[["compromisos","pagos","obligaciones"]].sum()
        gastos_disp = gastos.copy()
        for col in ["compromisos","pagos","obligaciones"]:
            gastos_disp[col] = gastos_disp[col].apply(format_cop)
        st.write("### Detalle GASTOS")
        st.markdown(gastos_disp.to_html(index=False), unsafe_allow_html=True)

        # Métrica total sin GASTOS
        st.metric("Total compromisos (sin GASTOS)", format_cop(tot["compromisos"]))

        # Consolidado de GASTOS por vigencia
        vigencias = ["VIGENCIA ACTUAL","RESERVAS","VIGENCIAS FUTURAS - RESERVAS","CUENTAS POR PAGAR","VIGENCIAS FUTURAS - VIGENCIA ACTUAL"]
        df_consol = df_raw[df_raw["nom_vigencia_del_gasto"].str.strip().str.upper().isin(vigencias) & df_raw["nombre_cuenta"].str.strip().str.upper().eq("GASTOS")]
        consolidado = df_consol.groupby("nom_vigencia_del_gasto",as_index=False)[["compromisos","pagos","obligaciones"]].sum()
        tot_con = consolidado[["compromisos","pagos","obligaciones"]].sum()
        consolidado = pd.concat([consolidado, pd.DataFrame([{"nom_vigencia_del_gasto":"TOTAL",**tot_con.to_dict()}])], ignore_index=True)
        consolidado_disp = consolidado.copy()
        for col in ["compromisos","pagos","obligaciones"]:
            consolidado_disp[col] = consolidado_disp[col].apply(format_cop)
        st.write("### Consolidado de GASTOS por tipo de vigencia")
        st.markdown(consolidado_disp.to_html(index=False), unsafe_allow_html=True)

        # Total global de compromisos
        st.metric("Total compromisos para todas las vigencias", format_cop(tot_con["compromisos"]))

