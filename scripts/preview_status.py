"""Render the actual AppKit status images without starting input monitoring."""
from pathlib import Path
import AppKit as K
from lado.app import status_image

K.NSApplication.sharedApplication()
out=Path(__file__).resolve().parents[1]/"build/status-preview"
out.mkdir(parents=True,exist_ok=True)
for code in ("EN","RU"):
    for locked in (False,True):
        icon=status_image(code,locked)
        canvas=K.NSImage.alloc().initWithSize_((156,108))
        canvas.lockFocus()
        K.NSColor.colorWithCalibratedWhite_alpha_(.94,1).setFill()
        K.NSRectFill(((0,0),(156,108)))
        icon.drawInRect_fromRect_operation_fraction_(((0,0),(156,108)),((0,0),(0,0)),K.NSCompositingOperationSourceOver,1)
        canvas.unlockFocus()
        bitmap=K.NSBitmapImageRep.imageRepWithData_(canvas.TIFFRepresentation())
        data=bitmap.representationUsingType_properties_(K.NSBitmapImageFileTypePNG,{})
        data.writeToFile_atomically_(str(out/f'{code}{"-locked" if locked else ""}.png'),True)
print(out)
