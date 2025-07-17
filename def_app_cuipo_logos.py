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
# Formatos y utilidades
# ————————————————

def format_cop(x):
    try:
        val = float(str(x).replace(',', '').replace('$', ''))
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
        f"codigo_entidad='{codigo_entidad}' AND periodo='{periodo}'"
    )
    params = {"$select": ",".join(cols), "$where": where, "$limit": 10000}
    r = requests.get("https://www.datos.gov.co/resource/4f7r-epif.csv", params=params, timeout=30)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))

@st.cache_data(ttl=300)
def fetch_account_data(periodo: str, ambito_code: str):
    """Obtiene registros de la API para un período y ambito_codigo."""
    url = "https://www.datos.gov.co/resource/22ah-ddsj.json"
    params = {"$where": f"periodo='{periodo}' AND ambito_codigo='{ambito_code}'", "$limit": 50000}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())
    for col in ['presupuesto_inicial', 'presupuesto_definitivo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    return df

# ————————————————
# Carga inicial
# ————————————————

df_mun, df_dep, df_per = cargar_tablas_control()
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
      .sidebar-logo {{ position:absolute; bottom:100px; left:0; right:0; text-align:center; z-index:1000; pointer-events:none; }}
      .sidebar-logo img {{ width:150px; }}
      .sidebar-logo2 {{ position:absolute; bottom:-575px; left:50%; transform:translateX(-50%); width:100px; z-index:1000; }}
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
# Programación de Ingresos
# ————————————————

if pagina == "Programación de Ingresos":
    st.title("💰 Programación de Ingresos")

    nivel = st.selectbox("Nivel geográfico:", ["Municipios", "Gobernaciones"])
    if nivel == "Municipios":
        deps = sorted(df_mun["departamento"].dropna().astype(str).unique())
        dep = st.selectbox("Departamento:", deps)
        df_ent = df_mun[df_mun["departamento"] == dep]
        label = "Municipio"
    else:
        df_ent = df_dep
        label = "Gobernación"
    ent = st.selectbox(f"Selecciona {label}:", df_ent['nombre_entidad'].dropna().astype(str).unique().tolist())
    cod_ent = str(df_ent.loc[df_ent['nombre_entidad'] == ent, 'codigo_entidad'].iloc[0])

    per_lab = st.selectbox("Período puntual:", df_per['periodo_label'].tolist())
    per = str(df_per.loc[df_per['periodo_label'] == per_lab, 'periodo'].iloc[0])

    if st.button("Cargar ingresos"):
        with st.spinner("Cargando datos..."):
            st.session_state['df_ingresos'] = obtener_ingresos(cod_ent, per)

    if 'df_ingresos' in st.session_state:
        df_i = st.session_state['df_ingresos']
        st.subheader("1. Datos brutos de ingresos")
        st.dataframe(df_i, use_container_width=True)

        # Descarga brutos
        buf_raw = io.BytesIO()
        with pd.ExcelWriter(buf_raw, engine='openpyxl') as writer:
            df_i.to_excel(writer, index=False, sheet_name='Datos Brutos')
        buf_raw.seek(0)
        st.download_button(
            "⬇️ Descargar datos brutos en Excel",
            data=buf_raw,
            file_name="datos_brutos_ingresos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Filtrar ámbitos
        codigos = ["1","1.1","1.1.01.01.200","1.1.01.02.104","1.1.01.02.200","1.1.01.02.300","1.1.02.06.001","1.2.06","1.2.07"]
        ambito_series = df_i['ambito_codigo'] if 'ambito_codigo' in df_i.columns else pd.Series(['']*len(df_i))
        df_fil = df_i[ambito_series.fillna('').astype(str).isin(codigos)]

        # Resumen correcto
        resumen = df_fil.copy()
        # Convertir a millones
        for col in ['presupuesto_inicial','presupuesto_definitivo']:
            if col in resumen.columns:
                resumen[col] = resumen[col] / 1e6
        # Calcular total (millones)
        total_ing = resumen['presupuesto_definitivo'].sum() if 'presupuesto_definitivo' in resumen.columns else 0.0
        # Renombrar columnas
        resumen = resumen.rename(columns={
            'presupuesto_inicial':'Presupuesto Inicial',
            'presupuesto_definitivo':'Presupuesto Definitivo',
            'periodo':'Periodo',
            'codigo_entidad':'Código Entidad',
            'nombre_entidad':'Nombre Entidad',
            'ambito_codigo':'Ámbito Código',
            'ambito_nombre':'Ámbito Nombre',
            'nombre_cuenta':'Nombre Cuenta'
        })
        # Formatear para despliegue
        tabla = resumen.copy()
        if 'Presupuesto Inicial' in tabla.columns:
            tabla['Presupuesto Inicial'] = tabla['Presupuesto Inicial'].map(format_cop)
        if 'Presupuesto Definitivo' in tabla.columns:
            tabla['Presupuesto Definitivo'] = tabla['Presupuesto Definitivo'].map(format_cop)

        st.subheader("2. Resumen de ingresos filtrados (millones de pesos)")
        st.markdown(tabla.to_html(index=False, escape=False), unsafe_allow_html=True)
        st.subheader("3. Total Presupuesto Definitivo (INGRESOS) (millones de pesos)")
        st.metric("", format_cop(total_ing * 1e6))

        # Mostrar histórico
        if st.button("Mostrar histórico"):
            df_hist = obtener_ingresos(cod_ent)
            df_hist = df_hist[df_hist['ambito_nombre'].str.upper()=='INGRESOS']
            df_hist['periodo_dt'] = pd.to_datetime(df_hist['periodo'], format='%Y%m%d', errors='coerce')
            df_hist['year'] = df_hist['periodo_dt'].dt.year
            df_hist['md'] = df_hist['periodo_dt'].dt.strftime('%m%d')
            registros, current = [], df_hist['year'].max()
            for yr, grp in df_hist.groupby('year'):
                if yr!=current:
                    q4=grp[grp['md']=='1201']
                    if not q4.empty: registros.append(q4.loc[q4['periodo_dt'].idxmax()])
                else:
                    registros.append(grp.loc[grp['periodo_dt'].idxmax()])
            df_sel = pd.DataFrame(registros).sort_values('periodo_dt')
            if 'presupuesto_definitivo' not in df_sel.columns:
                st.error("No se encontró la columna 'presupuesto_definitivo'.")
            else:
                df_sel['Ingresos Nominales']=df_sel['presupuesto_definitivo']/1e6
                ipc_map={2021:111.41,2022:126.03,2023:137.09,2024:144.88}
                df_sel['ipc']=df_sel['periodo_dt'].dt.year.map(ipc_map)
                df_sel['Ingresos Reales']=df_sel['Ingresos Nominales']/df_sel['ipc']*100
                df_long=df_sel.melt(id_vars=['periodo_dt'],value_vars=['Ingresos Nominales','Ingresos Reales'],var_name='Tipo',value_name='Monto')
                chart=alt.Chart(df_long).mark_line(point=True).encode(
                    x=alt.X('periodo_dt:T',title='Periodo',axis=alt.Axis(format='%Y')),
                    y=alt.Y('Monto:Q',title='Ingresos Q4 (millones)',axis=alt.Axis(format='$,.0f')),
                    color='Tipo:N',tooltip=['periodo_dt','Tipo',alt.Tooltip('Monto:Q',format='$,.0f')]
                ).properties(width=700,height=350)
                st.subheader("4. Histórico INGRESOS Nominal vs Real (millones)")
                st.altair_chart(chart,use_container_width=True)

# ————————————————
# Ejecución de Gastos
# ————————————————

elif pagina == "Ejecución de Gastos":
    st.title("💸 Ejecución de Gastos")

    nivel = st.selectbox("Selecciona el nivel", ["Municipios", "Gobernaciones"])
    if nivel == "Municipios":
        departamentos = sorted(df_mun["departamento"].dropna().astype(str).unique())
        dep_sel = st.selectbox("Selecciona el departamento", departamentos)
        df_entidades = df_mun[df_mun["departamento"] == dep_sel]
        label_ent = "Selecciona el municipio"
    else:
        df_entidades = df_dep
        label_ent = "Selecciona la gobernación"
    ent_sel = st.selectbox(label_ent, df_entidades['nombre_entidad'].dropna().astype(str).unique().tolist())
    codigo_ent = str(df_entidades.loc[df_entidades['nombre_entidad']==ent_sel, 'codigo_entidad'].iloc[0])

    periodo_label_g = st.selectbox("Selecciona el periodo", df_per['periodo_label'].tolist())
    periodo = str(df_per.loc[df_per['periodo_label']==periodo_label_g, 'periodo'].iloc[0])

    if st.button("Cargar datos"):
        st.session_state['df_gastos'] = obtener_datos_gastos(codigo_ent, periodo)

    if 'df_gastos' in st.session_state:
        df_raw = st.session_state['df_gastos']
        st.subheader("### Datos brutos")
        st.dataframe(df_raw.style.format({
            'compromisos': format_cop,
            'pagos': format_cop,
            'obligaciones': format_cop
        }), use_container_width=True)

        buf_raw = io.BytesIO()
        with pd.ExcelWriter(buf_raw, engine='openpyxl') as writer:
            df_raw.to_excel(writer, sheet_name='DatosBrutos', index=False)
        st.download_button(
            "⬇️ Descargar Datos Brutos (Excel)",
            data=buf_raw,
            file_name='datos_brutos_gastos.xlsx',
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Reemplaza la lista a continuación con los códigos de cuenta que deseas filtrar
        cuentas_filtrar = df_raw['cuenta'].unique().tolist()  # O especifica una lista como ['1', '2', ...]
        df_filtered = df_raw[
            df_raw['cuenta'].isin(cuentas_filtrar) &
            df_raw['nom_vigencia_del_gasto'].fillna('').str.strip().str.upper().eq('VIGENCIA ACTUAL')
        ]

        resumen = (
            df_filtered
            .groupby(['cuenta','nombre_cuenta'], as_index=False)[['compromisos','pagos','obligaciones']]
            .sum()
        )
        resumen = resumen[resumen['nombre_cuenta'].str.upper() != 'GASTOS']
        tot = resumen[['compromisos','pagos','obligaciones']].sum()
        resumen = pd.concat([resumen, pd.DataFrame([{'cuenta':'','nombre_cuenta':'TOTAL', **tot.to_dict()}])], ignore_index=True)

        resumen_disp = resumen.rename(columns={
            'cuenta':'Cuenta','nombre_cuenta':'Nombre cuenta',
            'compromisos':'Compromisos','pagos':'Pagos','obligaciones':'Obligaciones'
        })
        resumen_disp[['Compromisos','Pagos','Obligaciones']] = (resumen_disp[['Compromisos','Pagos','Obligaciones']]/1e6).applymap(format_cop)

        st.subheader("### Resumen de compromisos, pagos y obligaciones por cuenta (en millones de pesos)")
        st.markdown(resumen_disp.to_html(index=False), unsafe_allow_html=True)

        gastos = (
            df_filtered[df_filtered['nombre_cuenta'].str.upper()=='GASTOS']
            .groupby(['cuenta','nombre_cuenta'], as_index=False)[['compromisos','pagos','obligaciones']]
            .sum()
        )
        gastos_disp = gastos.drop(columns=['cuenta','nombre_cuenta']).rename(columns={
            'compromisos':'Compromisos','pagos':'Pagos','obligaciones':'Obligaciones'
        })
        gastos_disp[['Compromisos','Pagos','Obligaciones']] = (gastos_disp[['Compromisos','Pagos','Obligaciones']]/1e6).applymap(format_cop)

        st.subheader("### Detalle GASTOS (en millones de pesos)")
        st.markdown(gastos_disp.to_html(index=False), unsafe_allow_html=True)

        vigencias = [
            "VIGENCIA ACTUAL","RESERVAS","VIGENCIAS FUTURAS - RESERVAS",
            "CUENTAS POR PAGAR","VIGENCIAS FUTURAS - VIGENCIA ACTUAL"
        ]
        consolidado = (
            df_raw[df_raw['nom_vigencia_del_gasto'].fillna('').str.strip().str.upper().isin(vigencias) &
                   df_raw['nombre_cuenta'].fillna('').str.strip().str.upper().eq('GASTOS')]
            .groupby('nom_vigencia_del_gasto', as_index=False)[['compromisos','pagos','obligaciones']]
            .sum()
        )
        tot_con = consolidado[['compromisos','pagos','obligaciones']].sum()
        consolidado = pd.concat([consolidado, pd.DataFrame([{'nom_vigencia_del_gasto':'TOTAL', **tot_con.to_dict()}])], ignore_index=True)

        consolidado_disp = consolidado.rename(columns={
            'nom_vigencia_del_gasto':'Vigencia del gasto','compromisos':'Compromisos',
            'pagos':'Pagos','obligaciones':'Obligaciones'
        })
        consolidado_disp[['Compromisos','Pagos','Obligaciones']] = (consolidado_disp[['Compromisos','Pagos','Obligaciones']]/1e6).applymap(format_cop)

        st.subheader("### Consolidado de GASTOS por tipo de vigencia (en millones de pesos)")
        st.markdown(consolidado_disp.to_html(index=False), unsafe_allow_html=True)

        st.metric("Total compromisos para todas las vigencias", format_cop(tot_con['compromisos']/1e6 * 1e6))

        buf_all = io.BytesIO()
        with pd.ExcelWriter(buf_all, engine='openpyxl') as writer:
            df_raw.to_excel(writer, sheet_name='DatosBrutos', index=False)
            resumen_disp.to_excel(writer, sheet_name='Resumen', index=False)
            gastos_disp.to_excel(writer, sheet_name='DetalleGastos', index=False)
            consolidado_disp.to_excel(writer, sheet_name='Consolidado', index=False)
        buf_all.seek(0)
        st.download_button(
            "⬇️ Descargar Todo (Excel)", data=buf_all,
            file_name='ejecucion_gastos_completo.xlsx',
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ————————————————
# Comparativa de Ingresos
# ————————————————

elif pagina == "Comparativa de Ingresos":
    st.title("📊 Comparativa Per Cápita (Media Aritmética)")
    st.sidebar.header("Parámetros de consulta")

    departamentos = sorted(df_mun['departamento'].dropna().astype(str).unique())
    departamento_sel = st.sidebar.selectbox("Departamento", departamentos)
    df_dep_comp = df_mun[df_mun['departamento'] == departamento_sel]
    municipio_sel = st.sidebar.selectbox("Municipio", df_dep_comp['nombre_entidad'].dropna().astype(str).unique())

    periodo_label_sel = st.sidebar.selectbox("Período (label)", df_per['periodo_label'].tolist())
    periodo_sel = str(df_per.loc[df_per['periodo_label'] == periodo_label_sel, 'periodo'].iloc[0])

    cuenta_sel = st.sidebar.selectbox("Cuenta", df_cuentas_control['Nombre de la Cuenta'].dropna().astype(str).unique())
    ambito_code_sel = str(
        df_cuentas_control.loc[
            df_cuentas_control['Nombre de la Cuenta'] == cuenta_sel,
            'Código Completo'
        ].iloc[0]
    )

    if st.sidebar.button("🚀 Ejecutar comparativa"):
        df_acct = fetch_account_data(periodo_sel, ambito_code_sel)
        if df_acct.empty:
            st.warning("No hay datos para esa cuenta y período.")
            st.stop()

        df_sum = (
            df_acct.groupby('nombre_entidad', as_index=False)['presupuesto_definitivo']
                   .sum()
        )
        df_sum = df_sum.merge(
            df_mun[['nombre_entidad','poblacion','categoria']],
            on='nombre_entidad',
            how='left'
        ).dropna(subset=['poblacion'])
        df_sum['per_capita'] = df_sum['presupuesto_definitivo'] / df_sum['poblacion']

        sel = df_sum[df_sum['nombre_ent entidad'] == municipio_sel]
        pc_sel = sel['per_capita'].iloc[0] if not sel.empty else 0.0
        cat = sel['categoria'].iloc[0] if not sel.empty else None

        pc_cat = df_sum[df_sum['categoria'] == cat]['per_capita'].mean() if cat else 0.0
        pc_all = df_sum['per_capita'].mean() if not df_sum.empty else 0.0

        df_bar = pd.DataFrame({
            'Tipo': [municipio_sel, f'Promedio Cat. ({cat})', 'Promedio País'],
            'COP per cápita': [pc_sel, pc_cat, pc_all]
        })
        df_bar['COP per cápita'] = df_bar['COP per cápita'].apply(format_cop)

        df_plot = pd.DataFrame({
            'Tipo': df_bar['Tipo'],
            'Value': [pc_sel, pc_cat, pc_all]
        })
        chart = alt.Chart(df_plot).mark_bar(cornerRadius=4).encode(
            x=alt.X('Tipo:N', title=''),
            y=alt.Y('Value:Q', title='COP per cápita', axis=alt.Axis(format='$,.0f')),
            color=alt.condition(alt.datum.Tipo == municipio_sel, alt.value('orange'), alt.value('steelblue')),
            tooltip=[alt.Tooltip('Tipo:N'), alt.Tooltip('Value:Q', format='$,.0f')]
        ).properties(width=600, height=400)
        st.altair_chart(chart, use_container_width=True)

        st.subheader('📋 Valores per cápita: media aritmética')
        st.table(df_bar.set_index('Tipo'))
































