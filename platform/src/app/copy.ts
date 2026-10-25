/** Every piece of interface copy, so it can be reviewed and translated in one place. */
export const copy = {
  appName: 'Agora',
  search: {
    label: 'Busca tu ciudad',
    placeholder: 'Busca tu ciudad',
  },
  settings: {
    label: 'Ajustes',
    basemap: 'Mapa base',
    basemaps: { map: 'Mapa', satellite: 'Satélite' },
    layers: 'Capas',
    streetNames: 'Nombres de calles',
    theme: 'Tema',
    themes: { auto: 'Auto', light: 'Claro', dark: 'Oscuro' },
    themeLabels: { auto: 'Tema automático (el del sistema)', light: 'Tema claro', dark: 'Tema oscuro' },
  },
  boundaries: {
    label: 'Límites',
    heading: 'Límites administrativos',
    modes: {
      auto: 'Automático',
      autonomous_communities: 'Comunidades autónomas',
      provinces: 'Provincias',
      municipalities: 'Municipios',
      census_districts: 'Distritos censales',
      census_sections: 'Secciones censales',
      cadastral_parcels: 'Parcelas urbanas',
      rural_polygons: 'Polígonos catastrales',
      postal_codes: 'Códigos postales',
    },
    /** Hover label of census units, which have a number but no name of their own. */
    unitLabels: {
      census_district: (district: string, municipality: string) => `Distrito ${district} · ${municipality}`,
      census_section: (district: string, section: string, municipality: string) =>
        `Distrito ${district} · Sección ${section} · ${municipality}`,
      postal_code: (code: string) => `Código postal ${code}`,
      parcel: (reference: string, municipality: string) => `Parcela ${reference} · ${municipality}`,
      rural_polygon: (polygon: string, municipality: string) => `Polígono ${polygon} · ${municipality}`,
    },
    autoHint: 'Cambia de nivel con el zoom',
    fixed: 'nivel fijado',
    sharedTerritory: 'territorio compartido',
  },
  detail: {
    close: 'Cerrar',
    /** What each kind of unit is called, under its name in the detail panel. */
    kinds: {
      autonomous_community: 'Comunidad autónoma',
      province: 'Provincia',
      municipality: 'Municipio',
      shared_territory: 'Territorio compartido entre municipios',
      census_district: 'Distrito censal',
      census_section: 'Sección censal',
      postal_code: 'Código postal',
      cadastral_parcel: 'Parcela urbana',
      rural_polygon: 'Polígono catastral',
    } as Record<string, string>,
    empty: 'Todavía no hay datos de esta unidad.',
  },
  controls: {
    fullscreen: { enter: 'Pantalla completa', exit: 'Salir de pantalla completa' },
    zoomIn: 'Acercar',
    zoomOut: 'Alejar',
  },
  locate: {
    label: 'Mi ubicación',
    denied: 'Permite el acceso a tu ubicación en el navegador.',
    unavailable: 'No se ha podido obtener tu ubicación.',
  },
  sidebar: {
    label: 'Barra lateral',
    views: { map: 'Mapa' },
    close: 'Cerrar panel',
  },
  mapView: {
    layers: 'Capas de datos',
    noLayers: 'Todavía no hay capas de datos.',
  },
  tileError: 'No se ha podido cargar el mapa base.',
  boundariesError: 'No se han podido cargar los límites. ¿Está en marcha el servidor de teselas?',
}
