/** A picture file as bare base64, the form the model pass takes (no `data:` prefix). */
export function pictureToBase64(file: Blob): Promise<string> {
  return new Promise((ok, fail) => {
    const reader = new FileReader();
    reader.onload = () => ok(String(reader.result).replace(/^data:[^,]*,/, ""));
    reader.onerror = () => fail(new Error("the picture could not be read"));
    reader.readAsDataURL(file);
  });
}
