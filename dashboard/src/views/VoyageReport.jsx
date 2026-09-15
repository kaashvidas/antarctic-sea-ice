import { useState } from 'react'
import MapView from '../components/MapView'
import DaySlider from '../components/DaySlider'
import Legend from '../components/Legend'
import DisclosureBanner from '../components/DisclosureBanner'
import SummaryHeader from './report/SummaryHeader'
import WarningsPanel from './report/WarningsPanel'
import IcebergPanel from './report/IcebergPanel'
import WeatherPanel from './report/WeatherPanel'
import Timeline from './report/Timeline'
import { outputUrl } from '../api'

export default function VoyageReport({ report, manifest, onPlanAnother }) {
  const [day, setDay] = useState(0)
  const [showSeaIce, setShowSeaIce] = useState(true)
  const [seaIceOpacity, setSeaIceOpacity] = useState(0.55)

  const bounds = [
    [manifest.bounds.lat_min, manifest.bounds.lon_min],
    [manifest.bounds.lat_max, manifest.bounds.lon_max],
  ]
  const maxDay = manifest.forecast_horizon_days
  const seaIceUrl = manifest.seaice_images[day] ? outputUrl(manifest.seaice_images[day]) : null

  const selectedDayEntry = report.day_by_day.find((d) => d.day === day) || report.day_by_day[0]

  return (
    <div className="report">
      <DisclosureBanner
        dataSources={report.disclosure.data_sources}
        note={`${report.disclosure.iceberg_thickness_note} ${report.disclosure.ice_class_table_note}`}
      />

      <SummaryHeader report={report} onPlanAnother={onPlanAnother} />

      <WarningsPanel icebergs={report.icebergs} />

      <div className="report-body">
        <div className="report-map-col">
          <div className="report-map-pane">
            <MapView
              bounds={bounds}
              optimizedPath={report.route_comparison.optimized.path}
              naivePath={report.route_comparison.naive.path}
              start={report.query.start}
              goal={report.query.goal}
              icebergs={report.icebergs}
              seaIceUrl={seaIceUrl}
              showSeaIce={showSeaIce}
              seaIceOpacity={seaIceOpacity}
              siteMarkers={manifest?.domain?.site_markers || []}
            />
            <Legend />
            <DaySlider
              day={day}
              maxDay={maxDay}
              onChange={setDay}
              forecastDate={manifest.forecast_date}
              showSeaIce={showSeaIce}
              onToggleSeaIce={setShowSeaIce}
              seaIceOpacity={seaIceOpacity}
              onOpacityChange={setSeaIceOpacity}
            />
          </div>
        </div>

        <div className="report-side-col">
          <WeatherPanel day={selectedDayEntry} />
          <IcebergPanel icebergs={report.icebergs} />
        </div>
      </div>

      <Timeline dayByDay={report.day_by_day} selectedDay={day} onSelectDay={setDay} />
    </div>
  )
}
