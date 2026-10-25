const env = import.meta.env

/** Tunable values in one place: basemap providers, the tile server and the map's initial view. */
export const config = {
  tiles: {
    /** Tile server (Martin): /{layer} gives each layer's TileJSON. */
    url: env.VITE_TILES_URL ?? 'http://localhost:3000',
  },
  boundaries: {
    /**
     * Automatic mode: each level shows from its zoom up to the next one's (the last, up to the
     * maximum). Each layer's tiles have their own zoom range, set when they're built.
     */
    autoFromZoom: {
      autonomous_communities: 0,
      provinces: 6,
      municipalities: 8,
      census_districts: 10,
      census_sections: 12,
      cadastral_parcels: 15,
    },
    /**
     * With a layer fixed, the map can't zoom out past this: further out it would load too many
     * units at once, or none (each is at least the zoom its tiles start at). The automatic mode
     * keeps the map's own minimum.
     */
    fixedMinZoom: {
      autonomous_communities: 3,
      provinces: 3,
      municipalities: 5,
      census_districts: 8,
      census_sections: 9,
      cadastral_parcels: 15,
      rural_polygons: 9,
      postal_codes: 7,
    },
  },
  map: {
    // MapLibre style JSON; OpenFreeMap needs no account or key.
    styleUrl: env.VITE_MAP_STYLE_URL ?? 'https://tiles.openfreemap.org/styles/positron',
    /** Used by the dark theme (same provider and attribution as `styleUrl`). */
    darkStyleUrl: env.VITE_MAP_DARK_STYLE_URL ?? 'https://tiles.openfreemap.org/styles/dark',
    /** IGN's PNOA orthophoto: covers Spain only, which is all the platform shows. */
    satellite: {
      tileUrl:
        'https://www.ign.es/wmts/pnoa-ma?service=WMTS&request=GetTile&version=1.0.0&layer=OI.OrthoimageCoverage&style=default&tilematrixset=GoogleMapsCompatible&format=image/jpeg&tilematrix={z}&tilerow={y}&tilecol={x}',
      attribution: 'PNOA cedido por © <a href="https://www.ign.es">Instituto Geográfico Nacional</a>',
    },
    /** First view: mainland Spain and the Balearic Islands, as [[west, south], [east, north]]. */
    initialBounds: [
      [-9.6, 35.9],
      [4.5, 43.9],
    ] as [[number, number], [number, number]],
    minZoom: 3,
    maxZoom: 19,
    /** Zoom after "my location", unless the map is already closer. */
    locateZoom: 14,
  },
}
