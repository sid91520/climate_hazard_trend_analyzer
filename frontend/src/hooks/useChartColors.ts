import { useEffect, useState } from 'react'

// Chart colours are passed to Recharts as SVG attributes, where CSS variables
// aren't reliable, so the light/dark values live here. They match globals.css.
const LIGHT = {
  bar: '#2a78d6', // blue: the yearly values
  rolling: '#eb6834', // orange: 5-year rolling mean
  trend: '#52514e', // neutral grey, dashed: fitted trend line (a reference, not data)
  grid: '#e4e3df',
  axis: '#52514e',
  surface: '#fcfcfb',
}
const DARK = {
  bar: '#3987e5',
  rolling: '#d95926',
  trend: '#c3c2b7',
  grid: '#33332f',
  axis: '#c3c2b7',
  surface: '#1a1a19',
}

export type ChartColors = typeof LIGHT

export function useChartColors(): ChartColors {
  // Start with light: Next.js also renders this on the server, where there is no
  // `window`. The effect switches to the real OS setting once in the browser.
  const [dark, setDark] = useState(false)
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setDark(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return dark ? DARK : LIGHT
}
