function result = matlab_probe(inputPath, outputDir)
% Fixed-format read/process/save/reopen probe for the registered Canon City case.
% This is stored-value arithmetic, not calibrated reflectance or an ENVI algorithm.
assert(~isfolder(outputDir), 'Probe output must be a new directory');
fid = fopen(inputPath, 'rb', 'ieee-le');
assert(fid >= 0, 'Input cannot be opened');
closer = onCleanup(@() fclose(fid));
raw = fread(fid, 640*400*6, '*uint8');
assert(numel(raw) == 640*400*6 && isempty(fread(fid, 1)), 'Unexpected input size');
cube = permute(reshape(raw, [640,400,6]), [2,1,3]);
subset = cube(1:16,1:16,:);
bandMean = mean(double(subset), 3);
mkdir(outputDir);
save(fullfile(outputDir,'subset.mat'), 'subset', 'bandMean');
reopened = load(fullfile(outputDir,'subset.mat'));
assert(isequal(reopened.subset, subset) && isequal(reopened.bandMean, bandMean));
result = struct('software','MATLAB','version',version,'shape',size(subset), ...
    'readback_equal',true,'operation','mean of six stored-value bands', ...
    'georeference','unknown; no map coordinates or physical areas assigned');
fidOut = fopen(fullfile(outputDir,'summary.json'),'w');
assert(fidOut >= 0); closerOut = onCleanup(@() fclose(fidOut));
fprintf(fidOut,'%s',jsonencode(result));
end
