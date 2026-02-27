# CLO3D Python API Reference
**Source:** https://developer.clo3d.com | **SDK Version:** v9.1.0 (CLO 2025.2.236)  
**Purpose:** Reference document for building a CLO3D MCP server. Python signatures only.

---

## Architecture Notes for MCP Integration

CLO plugins run **inside** the CLO application process, not as external processes. To connect an external MCP server to CLO:

1. **MCP server** — runs as an external process, receives tool calls from Claude
2. **Python bridge plugin** — runs inside CLO, registered via Plugin tab → Plugin Manager, listens on a socket/IPC channel
3. **Plugin executes API calls** based on commands received from MCP server

Python scripts (`.py`) can be registered as plugins directly via CLO's Plugin Manager — no compilation needed.

Import pattern for CLO Python plugins:
```python
import import_api
import export_api
import fabric_api
import pattern_api
import utility_api
import ApiTypes
```

---

## PATTERN_API

### Pattern Creation

```python
def CreatePatternWithPoints(_points : tuple) -> int
"""
@brief Create a pattern piece from a sequence of 3D points.
@param _points: tuple of (x, y, curvature) tuples. Curvature values: 0=straight line, 2=curve, 3=bezier
@return index of the created pattern
"""
# Example - rectangle:
rectPoints = ((0.0,-300.0,0),(0.0,-200.0,0),(100.0,-200.0,0),(100.0,-300.0,0))
pattern_api.CreatePatternWithPoints(rectPoints)

# Example - curved shape (3=bezier):
halfCirclePoints = ((0.0,200.0,0),(0.0,300.0,3),(100.0,300.0,0),(200.0,300.0,3),(200.0,200.0,0))
pattern_api.CreatePatternWithPoints(halfCirclePoints)
```

### Pattern Queries

```python
def GetPatternCount() -> int
"""@brief Get total number of pattern pieces in the current project"""

def GetPatternIndexFrom2DView(_scenePosX : float, _scenePosY : float) -> int
"""
@brief Get the pattern index at a given 2D view position
@return pattern index, or -1 if no pattern found at that position
"""

def GetSelectedPattern() -> int
"""@brief Get the index of the currently selected pattern"""

def GetSelectedPatternViaIndex(_index : int) -> int
"""@brief Get selected pattern using index"""
```

### Pattern Selection

```python
def SelectPatternViaIndex(_index : int) -> bool
"""@brief Programmatically select a pattern by index"""

def SelectPatternViaName(_name : str) -> bool
"""@brief Programmatically select a pattern by name"""
```

### Pattern Naming

```python
def GetPatternName(_patternIndex : int) -> str
"""@brief Get the name of a pattern by index"""

def SetPatternName(_patternIndex : int, _name : str) -> bool
"""@brief Set the name of a pattern"""
```

### Pattern Point Editing

```python
def MovePatternPoint(_patternIndex : int, _pointIndex : int, _x : float, _y : float) -> bool
"""
@brief Move a single pattern point to new X, Y coordinates
@param _patternIndex: target pattern index
@param _pointIndex: index of the point to move
@param _x, _y: new coordinates in mm
"""

def MovePatternPoints(_patternIndex : int, _pointIndices : list[int], _xList : list[float], _yList : list[float]) -> bool
"""@brief Move multiple pattern points at once"""
```

### Pattern Line Queries

```python
def GetLineCount(_patternIndex : int) -> int
"""@brief Get number of outline lines on a pattern"""

def GetPointCount(_patternIndex : int, _lineIndex : int) -> int
"""@brief Get number of points on a specific line of a pattern"""
```

### Sewing (Seam Lines)

```python
def AddSeamlinePairGroup(_patternAIndex : int, _lineAIndex : int, _patternBIndex : int, _lineBIndex : int, _directionA : bool, _directionB : bool) -> bool
"""
@brief Create a sewing relationship between two pattern piece edges
@param _patternAIndex: index of first pattern
@param _lineAIndex: index of the line on pattern A to sew
@param _patternBIndex: index of second pattern
@param _lineBIndex: index of the line on pattern B to sew
@param _directionA: stitch direction for A. True=forward, False=backward
@param _directionB: stitch direction for B. True=forward, False=backward
@return name of the created sewing group (wstring)
"""

def GetSeamlinePairGroupCount() -> int
"""@brief Get total number of sewing pair groups in the project"""

def GetSeamlinePairGroupName(_groupIndex : int) -> str
"""@brief Get the name of a sewing pair group by index"""

def GetSeamlinePairGroupIndexFromName(_groupName : str) -> int
"""@brief Get sewing pair group index by name. Returns -1 if not found."""

def GetSeamlinePairGroupListInPattern(_patternIndex : int) -> list[int]
"""@brief Get all sewing pair group indices that involve the given pattern"""
```

### Topstitching

```python
def AddSeamlineTopstitch(_patternIndex : int, _lineIndex : int) -> bool
"""@brief Add a topstitch to a seamline"""
```

### Pattern Transforms

```python
def SymmetryPatternPiece(_patternIndex : int) -> int
"""
@brief Create a mirrored copy of a pattern piece
@return index of the new mirrored pattern
"""

def SymmetryPatternPieceWithPatternName(_patternName : str) -> int
"""@brief Mirror a pattern piece by name"""

def InstancePatternPiece(_patternIndex : int) -> int
"""@brief Create an instanced (linked) copy of a pattern piece"""

def InstancePatternPieceWithPatternName(_patternName : str) -> int
"""@brief Instance a pattern piece by name"""

def UnfoldPatternPiece(_patternIndex : int, _lineIndex : int, _bHalfSymmetry : bool) -> bool
"""@brief Unfold a pattern piece along a line"""

def UnfoldPatternPieceWithPatternName(_patternName : str, _lineIndex : int, _bHalfSymmetry : bool) -> bool
"""@brief Unfold a pattern piece by name"""
```

### Pattern JSON (Key for MCP)

```python
def ImportPatternJSON(_filePath : str) -> bool
"""
@brief Import pattern data from a JSON file. 
Allows programmatic generation of complete pattern definitions.
@param _filePath: path to JSON file
"""

def ExportPatternJSON(_filePath : str) -> bool
"""
@brief Export all pattern data to a JSON file.
Useful for reading current pattern state.
@param _filePath: output path for JSON file
"""
```

### Arrangement

```python
def GetArrangementPoint(_patternIndex : int) -> tuple[float, float]
"""@brief Get the 3D arrangement position of a pattern piece"""

def SetArrangementPoint(_patternIndex : int, _x : float, _y : float, _z : float) -> bool
"""@brief Set the 3D position for a pattern piece on the avatar"""
```

### Simulation Properties

```python
def SetAddlThicknessCollision(_patternIndex : int, _value : float) -> None
"""@brief Set additional collision thickness for a pattern (affects simulation accuracy)"""

def GetAddlThicknessCollisionValue(_patternIndex : int) -> float
"""@brief Get additional collision thickness value"""
```

### UV

```python
def GetBackUVExpansion(_patternIndex : int) -> bool
"""@brief Check if back UV expansion is enabled"""

def SetBackUVExpansion(_patternIndex : int, _bExpand : bool) -> None
"""@brief Enable or disable UV expansion on the back face"""

def GetSideUVExpansion(_patternIndex : int) -> bool
"""@brief Check if side UV expansion is enabled"""

def SetSideUVExpansion(_patternIndex : int, _bExpand : bool) -> None
"""@brief Enable or disable UV expansion on the side face"""
```

### Pins

```python
def GetPinListSize() -> int
"""@brief Get the number of pins currently applied"""

def RemovePin(_pinNumber : int) -> bool
"""@brief Remove a specific pin by number"""

def RemoveAllPins() -> bool
"""@brief Remove all pins from the garment"""
```

### Object Browser

```python
def ExportObjectBrowserMaterialList() -> str
"""@brief Get the item list within the object browser as JSON"""
```

---

## FABRIC_API

### Fabric Management

```python
def GetFabricCount(_bCurrentColorway : bool = True) -> int
"""
@brief Get number of fabrics in object browser
@param _bCurrentColorway: if True, count only fabrics in current colorway
"""

def GetFabricCount(_colorwayIndex : int) -> int
"""
@param _colorwayIndex: -2=all colorways, -1=current colorway, >=0=specific colorway
"""

def GetCurrentFabricIndex() -> int
"""@brief Get index of currently selected fabric"""

def SetCurrentFabricIndex(_index : int) -> bool
"""@brief Set the currently active fabric"""

def AddFabric(inputFilePath : str) -> int
"""
@brief Add a fabric to the object browser
@param inputFilePath: path to .zfab or .jfab file
@return index of the added fabric
"""

def ReplaceFabric(_fabricIndex : int, _inputFilePath : str) -> bool
"""@brief Replace a fabric in the object browser with a new one"""

def DeleteFabric(fabricIndex : int) -> bool
"""@brief Delete a fabric (affected patterns revert to default fabric)"""

def GetFabricName(fabricIndex : int) -> str
"""@brief Get fabric name by index"""

def SetFabricName(index : int, str : str) -> None
"""@brief Change the name of a fabric"""

def GetFabricIndex(fabricName : str) -> int
"""@brief Get fabric index by name. Returns -1 if not found."""
```

### Fabric Assignment

```python
def AssignFabricToPattern(_fabricIndex : int, _patternIndex : int, _assignOption : int) -> bool
"""
@brief Assign a fabric to a pattern piece
@param _fabricIndex: fabric index in object browser
@param _patternIndex: pattern index
@param _assignOption:
  1 = Current Colorway only
  2 = All Colorways (unlinked materials - each colorway gets own copy)
  3 = All Colorways (linked - changes apply to all simultaneously)
@return True if successful
"""

def GetFabricIndexForPattern(patternIndex : int) -> int
"""@brief Get the fabric index assigned to a specific pattern"""
```

### Fabric Properties

```python
def GetFabricWidth(fabricIndex : int) -> float
"""@brief Get fabric width in mm"""

def SetFabricWidth(_fabricIndex : int, mm : float) -> None
"""@brief Set fabric width in mm"""

def GetFabricLength(fabricIndex : int) -> float
"""@brief Get fabric length in mm"""

def GetFabricInfo(fabricIndex : int) -> str
"""@brief Get full fabric information as JSON string"""

def GetFabricInformation(_fabricIndex : int) -> map[str, str]
"""@brief Get fabric information as key-value map"""

def SetFabricInformation(_fabricIndex : int, _infoMap : map[str, str]) -> None
"""
@brief Set fabric information
@param _infoMap: keys include Classification, Content, SupplierName, Owner
"""
```

### PBR Material Colors

```python
def SetFabricPBRMaterialBaseColor(fabricIndex : int, materialFace : int, r : float, g : float, b : float, a : float) -> bool
"""
@brief Set base color of PBR material using RGBA values (0.0-1.0)
@param materialFace: 0=Front, 1=Back, 2=Side
"""

def SetFabricPBRMaterialBaseColor(fabricIndex : int, materialFace : int, _colorName : str) -> bool
"""@brief Set base color using a named color string"""

def GetFabricPBRMaterialBaseColor(fabricIndex : int, materialFace : int) -> tuple[float, float, float, float]
"""@brief Get base color as RGBA float tuple"""
```

### Texture Mapping

```python
def SetTextureMapping(fabricIndex : int, mappingType : int) -> None
"""
@brief Set texture mapping type
@param mappingType: 0=Repeat, 1=Unified
"""

def GetFabricTextureMappingType(_fabricIndex : int) -> int
"""
@brief Get texture mapping type
@return 0=Repeat, 1=Unified, -1=invalid index
"""
```

### Fabric Files

```python
def ExportZFab() -> str
"""@brief Export currently selected fabric as .zfab to CLO temp folder"""

def ExportZFab(filePath : str, index : int) -> str
"""@brief Export specific fabric by index to file path"""

def ChangeFabricWithJson(fabricIndex : int, inputJsonFilePath : str) -> bool
"""@brief Overwrite all fabric properties from a .jfab JSON file"""

def CreateZfabFromTextures(_filePath : str, _baseTexturePath : str, _normalTexturePath : str, _disPlacementTexturePath : str, _opacityTexturePath : str, _roughnessTexturePath : str, _metalnessTexturePath : str) -> bool
"""@brief Create a .zfab file from individual texture maps"""

def CombineZfab(_filePath : str, _baseZfabPath : str, _targetZfabPath : str) -> None
"""@brief Merge two zfab files: physical properties from base, image from target"""

def ImportGLTFAsFabric(_filePath : str) -> int
"""@brief Import a glTF/glB file as a fabric material"""
```

### Substance Materials

```python
def ImportSubstanceFile(fabricIndex : int, substanceFilePath : str) -> bool
"""@brief Import a Substance (.sbsar) file onto a fabric"""

def ImportSubstanceFileAsFaceType(_fabricIndex : int, _substanceFilePath : str, _faceType : str) -> bool
"""
@brief Import substance file onto a specific face
@param _faceType: "Front", "Back", or "Side"
"""

def SetSubstancePreset(fabricIndex : int, materialFace : int, presetIndex : int) -> None
"""@brief Set substance preset by index"""

def SetSubstanceResolution(fabricIndex : int, materialFace : int, resolutionIndex : int) -> None
"""@brief Set substance texture resolution"""
```

### Roughness

```python
def GetRoughnessType(_index : int, _materialFace : int) -> int
"""@return 0=Intensity, 1=Map"""

def SetRoughnessType(_index : int, _materialFace : int, _roughnessType : int) -> None
"""@param _roughnessType: 0=Intensity, 1=Map"""

def GetRoughnessValueIntensity(_index : int, _face : int) -> int
"""@brief Get roughness intensity value"""

def SetRoughnessValueIntensity(_fabricIndex : int, _face : int, _value : int) -> None
"""@brief Set roughness intensity value"""
```

### Colorway-Specific Fabric

```python
def GetColorwayFabricInfo(_colorwayIndex : int, _fabricIndex : int) -> str
"""@brief Get fabric info for a specific colorway as JSON"""

def GetSpecificColorwayFabricInfo(_colorwayIndex : int, _fabricIndex : int) -> str
"""@brief Get detailed fabric information for a specific colorway"""
```

### Metadata

```python
def GetAPIMetaData(fabricIndex : int) -> str
"""@brief Get custom API metadata for a fabric as JSON"""

def SetAPIMetaData(fabricIndex : int, jsonStr : str) -> bool
"""@brief Set custom API metadata on a fabric"""

def ChangeMetaDataValueForFabric(fabricIndex : int, metaDataKey : str, metaDataValue : str) -> None
"""@brief Update a single metadata key-value pair on a fabric"""
```

---

## IMPORT_API

```python
def ImportFile(_filePath : str) -> bool
"""
@brief Import a file into CLO. Supports: .avt, .zpac, .zprj, .zfab, .mtn, .zacs, .zcmr, .zvrp
Shows dialog if only path is provided.
"""

def ImportAvatar(_filePath : str, _options : ImportExportOption) -> bool
"""@brief Import an avatar file (.avt) with options"""

def ImportPose(_filePath : str, _avatarIndex : int) -> bool
"""@brief Load a pose file and apply to corresponding avatar"""

def ImportTrim(_filePath : str) -> bool
"""@brief Load a trim file into the scene"""

def ImportPatternJSON(_filePath : str) -> bool
"""@brief Import pattern data from JSON (see PATTERN_API)"""

def ImportAsGraphic(_filePath : str) -> bool
"""@brief Add an image as a graphic overlay on a pattern"""

def ImportGLTFAsFabric(_filePath : str) -> int
"""@brief Import glTF/glB as a fabric material"""

def ImportZpac(_filePath : str, _options : ImportExportOption) -> bool
"""@brief Import .zpac file with options to suppress dialog"""
```

---

## EXPORT_API

### Project Files

```python
def ExportZPac() -> str
"""@brief Export project as .zpac to CLO temp folder. Returns file path."""

def ExportZPac(_filePath : str) -> str
"""@brief Export project as .zpac to specified path"""

def ExportZPrj() -> str
"""@brief Export project as .zprj to CLO temp folder"""

def ExportZPrj(_filePath : str, _bCreateThumbnail : bool) -> str
"""@brief Export .zprj with optional thumbnail PNG"""
```

### 3D Mesh Exports

```python
def ExportOBJ() -> list[str]
"""@brief Export as OBJ. Returns list of file paths (OBJ + MTL files per colorway)."""

def ExportOBJ(_filePath : str, _options : ImportExportOption) -> list[str]
"""@brief Export OBJ with options"""

def ExportGLTF(_filePath : str, _options : ImportExportOption, _bGLBinary : bool) -> list[str]
"""@brief Export as GLTF"""

def ExportGLB(_filePath : str, _options : ImportExportOption) -> list[str]
"""@brief Export as GLB (binary GLTF)"""

def ExportFBX(_filePath : str, _options : ImportExportOption) -> list[str]
"""@brief Export as FBX"""

def ExportUSD(_filePath : str, _options : ImportExportOption, _usdOptions : ExportUSDOption) -> list[str]
"""@brief Export as USD"""

def ExportAlembic(_filePath : str, _options : ImportExportOption) -> list[str]
"""@brief Export as Alembic animation format"""
```

### Pattern Exports

```python
def ExportDXF(_filePath : str, _exportOption : ExportDxfOption) -> str
"""@brief Export patterns as DXF (for cutting machines/CAD). No dialog with options param."""

def ExportPatternJSON(_filePath : str) -> bool
"""@brief Export pattern data as JSON (see PATTERN_API)"""
```

### Images & Renders

```python
def ExportThumbnail3D() -> str
"""@brief Export 3D viewport screenshot to temp folder"""

def ExportThumbnail3D(_filePath : str) -> str
"""@brief Export 3D viewport screenshot to path"""

def ExportSnapshot3D(_filePath : str) -> list[list[str]]
"""@brief Export snapshot (shows CLO dialog). Returns paths per colorway."""

def ExportRenderingImage(_filePath : str, _bRenderAllColorways : bool, _startIndex : int) -> list[list[str]]
"""@brief Export rendered image(s). Returns paths per colorway."""

def ExportSingleColorwayRenderingImage(_filePath : str, _colorwayIndex : int, _startIndex : int) -> list[str]
"""@brief Export rendered image for a single colorway"""

def ExportTurntableImages(_filePath : str, _numberOfImages : int, _width : int, _height : int, _startIndex : int) -> list[str]
"""
@brief Export turntable image sequence
@param _numberOfImages: count of images for full 360° turn
@param _width, _height: image dimensions in pixels
"""

def ExportTurntableImagesByColorwayIndex(_filePath : str, _numberOfImages : int, _colorwayIndex : int, _width : int, _height : int) -> list[str]
"""@brief Export turntable images for a specific colorway"""

def ExportCustomViewSnapshot(_targetFolderPath : str, _width : int, _height : int, _outputPrefix : str) -> list[str]
"""@brief Export snapshots of all Custom Views"""

def ExportStdViewImage(_viewIndex : int, _outputFolderPath : str, _colorwayIndex : int, _width : int, _height : int) -> str
"""@brief Export standard view image by view index"""

def ExportStdViewImageForAllColorways(_viewIndex : int, _outputFolderPath : str, _width : int, _height : int) -> str
"""@brief Export standard view for all colorways"""
```

### Video

```python
def ExportTurntableVideo() -> str
"""@brief Export turntable video (requires XVid codec)"""

def ExportAnimationVideo(_filePath : str) -> str
"""@brief Export animation video"""
```

### Tech Pack & BOM

```python
def ExportTechPack(_filePath : str, _exportOption : ExportTechpackOption) -> None
"""
@brief Export tech pack as JSON + associated images
@param _filePath: must be *.json format
"""

def ExportTechPackToStream(_outputImageFolderPath : str) -> str
"""@brief Export tech pack data as JSON string (returns string directly)"""

def ExportBOM(_filePath : str) -> bool
"""@brief Export Bill of Materials as CSV"""

def ExportPOM(_filePath : str) -> str
"""@brief Export Points of Measure"""

def ExportPOM(_bInclude3DLength : bool, _filePath : str) -> str
"""@brief Export POM with optional 3D length data"""
```

### Garment Information

```python
def ExportGarmentInformation(_filePath : str) -> str
"""@brief Export garment info (same as File > Information > Garment) as JSON"""

def ExportGarmentInformationToStream() -> str
"""@brief Get garment information as JSON string directly"""
```

### Colorway Info

```python
def GetColorwayCount() -> int
"""@brief Get number of colorways in current garment"""

def GetCurrentColorwayIndex() -> int
"""@brief Get index of active colorway"""

def GetColorwayNameList() -> list[str]
"""@brief Get names of all colorways"""

def GetAvatarCount() -> int
"""@brief Get number of avatars loaded"""

def GetAvatarNameList() -> list[str]
"""@brief Get names of all avatars"""

def GetAvatarGenderList() -> list[int]
"""@return list of gender ints: 0=male, 1=female, -1=unknown"""
```

### Custom Views / ZCMR

```python
def ExportZCMR(_folderPath : str) -> list[str]
"""@brief Export all custom view ZCMR files"""

def GenerateZcmrFrom3DWindow(_filePath : str, _addToList : bool) -> list[str]
"""@brief Capture current 3D window and save as ZCMR"""

def LoadCustomViewIn3DWindow(_index : int) -> bool  # via utility_api
"""@brief Load a saved custom view into 3D window by index"""
```

### Avatar Export

```python
def ExportAVT(_filePath : str) -> str
"""@brief Export avatar as .avt file"""

def ExportPose(_filePath : str) -> str
"""@brief Export current avatar pose"""
```

---

## UTILITY_API

### Simulation

```python
def Simulate(_frame : int) -> None
"""
@brief Run cloth simulation
@param _frame: number of frames to simulate
"""

def SetStartAnimationFrame(_frame : int) -> None
def SetEndAnimationFrame(_frame : int) -> None
def SetAnimationRecording(_bRecord : bool) -> None
def GetTotalEndAnimationFrame() -> int
def GetAnimationLayerFrameRange(_layerIndex : int) -> tuple[int, int]
```

### Avatar

```python
def GetCLOAssetFolderPath(_bUserFolder : bool) -> str
"""@brief Get path to CLO assets folder"""

def SetAvatarActivation(_avatarName : str, _bActivate : bool) -> None
"""@brief Activate or deactivate an avatar by name"""

def DeleteAvatar(_avatarIndices : list[int]) -> bool
"""@brief Delete avatars by index list"""

def SetAvatarTextureMap(_avatarIndex : int, _mapType : int, _filePath : str) -> None
"""
@brief Assign texture map to avatar
@param _mapType: 0=BaseColor, 1=Metallic, 2=Normal, 3=Roughness, 5=Displacement
"""

def SetAvatarProperties(_avatarIndex : int, _properties : dict) -> None
def GetAvatarProperties(_avatarIndex : int) -> dict

def SetAvatarSmooth(_maxSubdivLevel : int) -> None
def GetAvatarSubdivisionLevel() -> int

def SetAvatarSoftBodyStiffness(_avatarIndex : int, _stiffness : float) -> None
def GetAvatarSoftBodyStiffness(_avatarIndex : int) -> float
```

### Camera / View

```python
def SetCamViewPoint(_viewIndex : int) -> None
"""
@brief Set camera to a standard viewpoint
@param _viewIndex: 0=bottom, 1=3/4right, 2=front, 3=3/4left, 4=right, 5=top, 6=left, 7=focus zoom, 8=back, 9=zoom extents all
"""

def SetViewPoint(_index : int) -> None
"""@brief Set view point by index"""

def GetViewPoint() -> int
"""@brief Get current view point index"""

def SetZoomView(_zoomLevel : float) -> None
"""@brief Set zoom level"""

def SetZoomCloth() -> None
"""@brief Zoom to fit the cloth"""

def SetViewControlDefaults(_xAngle : float, _yPosition : float, _cameraDistance : float) -> None
"""@brief Set default 3D view parameters"""

def FitAllUV() -> None
"""@brief Fit all patterns within UV editor cell"""
```

### Colorways

```python
def GetColorwayCount() -> int
def GetCurrentColorwayIndex() -> int
def SetCurrentColorwayIndex(_index : int) -> None
def GetColorwayNameList() -> list[str]
def SetColorwayName(_colorwayIndex : int, _name : str) -> None
def CopyColorway(_colorwayIndex : int) -> int
"""@brief Duplicate a colorway. Returns index of new colorway."""
def UpdateColorways(_bUpdateAll : bool) -> None
def SetNestingTargetColorway(_colorwayIndex : int) -> None
def GetNestingTargetColorway() -> int
```

### Display / Visibility

```python
def SetGarmentDisplayProperties(_propertyType : int, _bShow : bool) -> None
"""
@brief Toggle garment-related visibility
@param _propertyType: 0=Garment, 1=ArchivedPattern, 2=Seamlines, 3=InternalLines, 4=Baselines, 5=3DPen, 6=Threads, 7=Pins, 8=GarmentMeasurements, 9=2DMeasurements, 10=FittingSuit, 11=All
"""

def SetEnvironmentDisplayProperties(_propertyType : int, _bShow : bool) -> None
"""
@param _propertyType: 0=Light3D, 1=LightRender, 2=WindController, 3=3DShadow, 4=GroundGrid, 5=Grid, 6=All
"""

def SetShowHideColorOptions(_optionType : int, _bShow : bool) -> None
"""
@param _optionType: 0=All, 1=Freeze, 2=Strengthen, 3=Solidify, 4=Layer, 5=AllMesh, 6=SubdivideMesh, 7=FreezeMesh, 8=StrengthenMesh, 9=SolidifyMesh
"""

def SetTrimDisplaySettings(_trimType : int, _bShow : bool) -> None
"""
@param _trimType: 0=Button, 1=Pipings, 2=BondSkive, 3=Puckering, 4=AllTrims, 5=All
"""

def Set3DGarmentRenderingStyle(_style : int) -> None
def Get3DGarmentRenderingStyle() -> int

def SetShowHideAvatar(_bShow : bool) -> None
def IsShowAvatar() -> bool

def SetSchematicRender(_bEnable : bool) -> None
"""@brief Enable/disable schematic (flat) render mode"""
```

### Background & Formatting

```python
def SetFormat3DBackground(_r : int, _g : int, _b : int) -> None
"""@brief Set 3D background color via RGB values (0-255)"""
```

### Rendering & Quality

```python
def GetQualityRender() -> bool
def SetQualityRender(_bEnable : bool) -> None
```

### Nesting / UV

```python
def ResetUVto2DArrangement() -> None
"""@brief Match pattern arrangement in 2D to UV layout"""

def StartNesting() -> None
"""@brief Start automatic pattern nesting"""
```

### Hanging

```python
def AutoHang(_garmentPath : str, _hangerPath : str, _hangType : int, _options : ImportExportOption) -> None
"""
@brief Automatically hang a garment onto a hanger
@param _hangType: 0=top hanger, 1=bottom hanger
"""
```

### Plugins

```python
def AddPluginFromFile(_filePath : str) -> bool
"""@brief Add a DLL/DYLIB/.py file to the plugin list"""

def RemovePluginFromList(_filePath : str) -> bool
"""@brief Remove a plugin from the list"""
```

### Schematic (Technical Drawing)

```python
def SetSchematicSilhouetteLineWidth(_width : float) -> None
def SetSchematicSeamlineWidth(_width : float) -> None
```

### Zipper APIs (v9.0.0+)

```python
def SetZipperStyleName(_styleIndex : int, _name : str) -> None
def GetZipperStyleName(_styleIndex : int) -> str
def SetZipperStyleFunctionType(_styleIndex : int, _type : int) -> None
def GetZipperStyleFunctionType(_styleIndex : int) -> int
def SetZipperStyleTeethType(_styleIndex : int, _type : int) -> None
def GetZipperStyleTeethType(_styleIndex : int) -> int
def SetZipperSliderStyle(_styleIndex : int, _sliderStyle : str) -> None
def SetZipperPullerStyle(_styleIndex : int, _pullerStyle : str) -> None
def SetZipperStyleTeethWidth(_styleIndex : int, _width : float) -> None
def GetZipperStyleTeethWidth(_styleIndex : int) -> float
def SetZipperStyleWeight(_styleIndex : int, _weight : float) -> None
def SetZipperStyleTapeThickness(_styleIndex : int, _thickness : float) -> None
```

### Trim Styles

```python
def GetTrimStyleCount() -> int
def GetTrimStyleIndex(_name : str) -> int
"""@return index or -1 if not found"""
def GetTrimStyleName(_index : int) -> str
```

### TopStitch Styles

```python
def GetTopStitchCount() -> int
def GetTopStitchIndex(_name : str) -> int
def GetTopStitchName(_index : int) -> str
```

### Graphic Styles

```python
def AddGraphicStyleToPattern(_patternIndex : int, _x : float, _y : float, _width : float, _height : float, _faceSide : int, _zOffset : float, _rotationAngle : float) -> bool
"""@brief Place a graphic style onto a pattern at specified coordinates"""

def GetGraphicStylePosition(_styleIndex : int) -> dict
"""@brief Get position information for a graphic object"""

def GetGraphicStyleColor(_styleIndex : int) -> tuple
"""@brief Get color info for a graphic"""

def SetGraphicStyleColor(_styleIndex : int, _colorName : str) -> None
"""@brief Set graphic color by color name"""

def Get_Set_GraphicStyleName(_index : int) -> str
# GetGraphicStyleName / SetGraphicStyleName available
```

### Modular

```python
def AddLineToCategory(_categoryName : str) -> bool
"""@brief Create a line with all styles if none exist, or add line to category"""

def AddBlockTypeToStyle(_blockType : str, _styleName : str, _categoryName : str, _lineName : str) -> bool
"""@brief Add a block type (body, sleeve, collar, etc.) to a style"""
```

### Measurements

```python
def ImportAvatarMeasure(_filePath : str) -> bool
"""@brief Import measurement data and apply to avatar"""
```

### File Operations

```python
def GetCLOTemporaryFolderPath() -> str
"""@brief Get the path to CLO's temporary output folder"""

def SaveCLOFileThumbnail(_filePath : str) -> str
"""@brief Save the CLO file's thumbnail image"""
```

### Property Window

```python
def UpdatePropertyWindow() -> None
"""@brief Refresh the property window"""
```

---

## REST_API

CLO exposes a built-in REST API for external HTTP communication. Supports GET, POST, PUT. Useful as an alternative IPC mechanism to sockets.

```python
# REST API is accessed via HTTP requests to CLO's local server
# Multi-thread support available
# Can be used as an alternative to socket-based IPC for MCP bridge
```

---

## ApiTypes (Data Structures)

### ImportExportOption

```python
class ImportExportOption:
    scale: float          # Scale factor (e.g., 1=1mm, 10=10cm)
    bSaveInZip: bool      # If True, zip output files
    bLoadDisplaySettings: bool  # Load display settings from file (zprj)
    # Additional options vary by export format
```

### ExportDxfOption

```python
class ExportDxfOption:
    # DXF-specific export settings
    pass
```

### ExportTechpackOption

```python
class ExportTechpackOption:
    # Techpack export settings, includes authentication keys for enterprise features
    pass
```

### ExportUSDOption

```python
class ExportUSDOption:
    # USD-specific export settings
    pass
```

---

## API Scenario Examples

### Complete Garment Setup Workflow

```python
import import_api, utility_api, fabric_api, pattern_api, export_api
import ApiTypes

# 1. Load avatar
import_api.ImportFile("path/to/avatar.avt")

# 2. Load garment
import_api.ImportFile("path/to/garment.zpac")

# 3. Run simulation
utility_api.Simulate(100)

# 4. Load and assign fabric
fabric_index = fabric_api.AddFabric("path/to/fabric.zfab")
pattern_count = pattern_api.GetPatternCount()
for i in range(pattern_count):
    fabric_api.AssignFabricToPattern(fabric_index, i, 1)  # 1=current colorway

# 5. Export
export_api.ExportRenderingImage("output/render.png", False, 0)
export_api.ExportOBJ("output/garment.obj")
export_api.ExportTechPack("output/techpack.json", ApiTypes.ExportTechpackOption())
```

### Create Pattern Pieces and Sew

```python
import pattern_api

# Create front bodice rectangle (x, y, curvature)
# curvature: 0=straight, 2=curve, 3=bezier
front = pattern_api.CreatePatternWithPoints((
    (0.0, 0.0, 0),
    (0.0, 500.0, 0),
    (300.0, 500.0, 0),
    (300.0, 0.0, 0)
))
pattern_api.SetPatternName(front, "Front_Bodice")

# Create back bodice
back = pattern_api.CreatePatternWithPoints((
    (400.0, 0.0, 0),
    (400.0, 500.0, 0),
    (700.0, 500.0, 0),
    (700.0, 0.0, 0)
))
pattern_api.SetPatternName(back, "Back_Bodice")

# Sew side seams
# Need to know line indices - use GetLineCount to query
front_line_count = pattern_api.GetLineCount(front)
back_line_count = pattern_api.GetLineCount(back)

# Sew right side seam (line indices depend on pattern geometry)
pattern_api.AddSeamlinePairGroup(front, 2, back, 0, True, True)
```

### Colorway Workflow

```python
import utility_api, fabric_api

# Load garment first...
target_fabric = fabric_api.GetFabricCount() - 1

for i in range(3):
    # Copy last colorway
    colorway_count = utility_api.GetColorwayCount()
    new_index = utility_api.CopyColorway(colorway_count - 1)
    utility_api.SetCurrentColorwayIndex(new_index)

    # Name it
    utility_api.SetColorwayName(new_index, f"Colorway {chr(ord('A') + i)}")

    # Set color (materialFace: 0=Front)
    colors = [(1,0,0), (0,1,0), (0,0,1)]
    r, g, b = colors[i]
    fabric_api.SetFabricPBRMaterialBaseColor(new_index, target_fabric, 0, r, g, b, 1.0)

utility_api.UpdateColorways(True)
```

### Auto Hanging

```python
import utility_api
import ApiTypes

garment = utility_api.GetCLOAssetFolderPath(True) + "Garment/Male_T-shirt.zpac"
hanger = utility_api.GetCLOAssetFolderPath(True) + "Avatar/Hanger/Adult_Shirt_Hanger_V3.avt"

obj_option = ApiTypes.ImportExportOption()
obj_option.scale = 1  # 1mm scale

utility_api.AutoHang(garment, hanger, 0, obj_option)  # 0=top hanger
```

---

## Event Plugin System

For reactive workflows (e.g., respond to drag-and-drop), CLO supports an Event Plugin system:

```cpp
// C++ only - must be compiled as DLL/DYLIB
// Hooks available:
bool MouseDropEventOn2DView(float _scenePosX, float _scenePosY, 
    const std::unordered_map<std::string, std::vector<std::string>>& _mimeData)

// Inside the handler you can call any API:
auto patternAPI = CLOAPI::APICommand::getInstance().GetPatternAPI();
auto fabricAPI = CLOAPI::APICommand::getInstance().GetFabricAPI();
```

---

## Plugin Registration

Python scripts are registered via: **CLO > Plugin tab > Plugin Manager > + ADD**

Supported file types: `.dll` (Windows C++), `.dylib` (macOS C++), `.py` (Python)

Default plugin folder locations:
- Windows: `%APPDATA%\CLO Virtual Fashion\CLO\plugin`
- Can be customized via `defaultPluginFolders.txt`

---

## MCP Bridge Architecture (Recommended)

```
Claude (MCP Client)
    ↓ tool calls
MCP Server (Python, external process)
    ↓ socket/named pipe
CLO Bridge Plugin (Python .py loaded inside CLO)
    ↓ direct function calls
CLO Python API (import_api, pattern_api, etc.)
    ↓
CLO Application
```

### Bridge Plugin Skeleton

```python
# clo_bridge_plugin.py — loaded inside CLO via Plugin Manager
import socket
import json
import threading
import pattern_api
import fabric_api
import export_api
import utility_api

def handle_command(command_json):
    cmd = json.loads(command_json)
    action = cmd["action"]
    params = cmd.get("params", {})
    
    if action == "create_pattern":
        points = [tuple(p) for p in params["points"]]
        idx = pattern_api.CreatePatternWithPoints(tuple(points))
        return {"success": True, "pattern_index": idx}
    
    elif action == "add_seam":
        result = pattern_api.AddSeamlinePairGroup(
            params["patternA"], params["lineA"],
            params["patternB"], params["lineB"],
            params["dirA"], params["dirB"]
        )
        return {"success": bool(result)}
    
    elif action == "simulate":
        utility_api.Simulate(params.get("frames", 100))
        return {"success": True}
    
    elif action == "export_obj":
        paths = export_api.ExportOBJ(params.get("path", ""))
        return {"success": True, "paths": paths}
    
    # ... additional commands
    
    return {"error": f"Unknown action: {action}"}

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 9876))
    server.listen(1)
    while True:
        conn, _ = server.accept()
        data = conn.recv(4096).decode()
        result = handle_command(data)
        conn.send(json.dumps(result).encode())
        conn.close()

threading.Thread(target=start_server, daemon=True).start()
```

---

## Changelog Highlights (Recent API Additions)

| Version | Added |
|---------|-------|
| v9.1.0 (Dec 2025) | TopStitch APIs, SetNormalBlendingMethod |
| v9.0.0 (Sep 2025) | Full Zipper APIs, SetAvatarProperties, GetAnimationLayerFrameRange |
| v8.0.3 (Aug 2025) | MovePatternPoint/s, GetTrimStyleCount, GetTopStitchCount, ExportZCMR |
| v8.0.2 (Jun 2025) | SymmetryPatternPiece, InstancePatternPiece, SelectPatternViaIndex/Name, AddGraphicStyleToPattern |
| v8.0.0 (Apr 2025) | SetAvatarTextureMap, DeleteAvatar, SetGarmentDisplayProperties, SetEnvironmentDisplayProperties |
| v7.0.0 (Dec 2024) | ExportUSD, AutoHanging, FocusZoom/ZoomExtendAll for SetCamViewPoint |
| v6.0.0-6.0.4 (2024) | Full colorway-aware fabric APIs, GetFabricIndexForPattern, ZCMR APIs |
| v4.3.2 (Jan 2024) | **AddSeamlinePairGroup**, ImportPatternJSON, ExportPatternJSON, GetSeamlinePairGroupCount/Name |
| v4.3.0 (Nov 2023) | ExportStdViewImage, ExportCustomViewImage, ExportMultiViewImages |

---

*Generated from https://developer.clo3d.com — SDK v9.1.0, CLO 2025.2.236*  
*For Claude Code: Use Python API only. C++ variants (W-suffix = wide string Unicode) are not needed for Python bridge plugin.*
