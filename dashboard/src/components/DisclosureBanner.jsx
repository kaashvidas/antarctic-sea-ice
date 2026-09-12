// Reads manifest.placeholder_inputs so the disclosure text stays accurate
// if the backend's placeholder list changes later — never hardcode it.
function humanize(fieldName) {
  return fieldName
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

export default function DisclosureBanner({ placeholderInputs }) {
  if (!placeholderInputs || placeholderInputs.length === 0) return null

  const list = placeholderInputs.map(humanize).join(', ')

  return (
    <div className="disclosure-banner" role="status">
      <span className="icon" aria-hidden="true">
        ⚠️
      </span>
      <span>
        <strong>Placeholder inputs:</strong> {list} are shown as stand-ins
        pending live NSIDC/ERA5 downloads. Routing and iceberg-drift physics
        are computed from real tracked-iceberg data.
      </span>
    </div>
  )
}
