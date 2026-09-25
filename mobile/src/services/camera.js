import { Camera, CameraResultType, CameraSource } from '@capacitor/camera'

export async function captureWorkOrderPhoto() {
  const image = await Camera.takePhoto({
    source: CameraSource.Camera,
    resultType: CameraResultType.Uri,
    quality: 82,
    targetWidth: 1600,
    targetHeight: 1600,
    correctOrientation: true,
    saveToGallery: false,
    includeMetadata: false,
  })
  if (!image.webPath) throw new Error('A kamera nem adott vissza képet.')
  const response = await fetch(image.webPath)
  const blob = await response.blob()
  const extension = image.format === 'png' ? 'png' : 'jpg'
  return new File([blob], `munkalap-${Date.now()}.${extension}`, { type: blob.type || `image/${image.format || 'jpeg'}` })
}
