/** @type {import('@capacitor/cli').CapacitorConfig} */
const config = {
  appId: 'hu.munkalap.technician',
  appName: 'Munkalap Technikus',
  webDir: 'dist',
  server: { androidScheme: 'https' },
  plugins: {
    CapacitorHttp: { enabled: true },
  },
}

export default config
