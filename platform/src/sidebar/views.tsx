import type { ReactNode } from 'react'
import { copy } from '../app/copy'
import { MapView } from './MapView'

export type ViewId = 'map'

export interface SidebarView {
  id: ViewId
  label: string
  /** 24 px icon for the activity bar. */
  icon: ReactNode
  content: ReactNode
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
    content: <MapView />,
  },
]
