import type { ReactNode } from 'react'
import { copy } from '../app/copy'

export type ViewId = 'map' | 'catalog'

export interface SidebarView {
  id: ViewId
  label: string
  /** 24 px icon for the activity bar. */
  icon: ReactNode
}

/** The activity bar's tabs, top to bottom; each opens its panel in the sidebar. */
export const views: SidebarView[] = [
  {
    id: 'map',
    label: copy.sidebar.views.map,
    icon: (
      <path
        d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Zm0 0v14m6-12v14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    ),
  },
  {
    id: 'catalog',
    label: copy.sidebar.views.catalog,
    icon: (
      <g fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round">
        <ellipse cx="12" cy="5.5" rx="7" ry="2.5" />
        <path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
      </g>
    ),
  },
]
