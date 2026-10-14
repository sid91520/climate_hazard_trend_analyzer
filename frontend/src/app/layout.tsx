import type { Metadata, Viewport } from 'next'
import 'leaflet/dist/leaflet.css'
import './globals.css'

export const metadata: Metadata = {
  title: 'Heatwave Trend Analyzer',
  description: 'How have heatwaves changed where you live? Trends from ERA5 climate reanalysis data.',
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
