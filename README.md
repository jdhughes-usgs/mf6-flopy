# frontier-flopy
Manuscript for frontier

# Outline

## Introduction

MODFLOW 6 supports multiple models (), multiple packages of the same type, unstructured grids, ... giving the statement of the problem

How we now handle support for rapidly evolving mf6 

* Rethinking how to handle new or changing input using automated Class Generation for Models and Packages; codevelopment of the simulation code and the FloPy support utilities at the same time using definition files as the common link.  Allows new mf6 capabilities to be immediately supported and testable with FloPy

* Support Structured and Unstructured Grids from the bottom up

* Implement new processing capabilities so that users can apidly construct modelsGeospatial Processing

* easier access of Model Results

## Common Modeling

### Generating grids

structured grid, triangular mesh, quadtree grid, voronoi

### Geospatial processing

Intersections, raster resampling, ...

### Plotting

### Exporting grid data to other formats

shapefiles (all grids), NetCDF and VTK export supported for structured grids


## Examples

Background of the McDonald Valley


## Conclusions
