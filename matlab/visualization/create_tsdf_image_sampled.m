function shapeSurfaceImage = ...
    create_tsdf_image_sampled(shapeParams, shapeSamples, scale, contrastRatio, black, vis)

if nargin < 4
    contrastRatio = 0.7;
end
if nargin < 5
    black = false;
end
if nargin < 6
    vis = false;
end

tsdf = shapeSamples{1}.tsdf;
gridDim = sqrt(size(tsdf,1));
% Alpha blend all samples
numSamples = size(shapeSamples,2);
dim = 2 * shapeParams.gridDim;
hd_dim = scale / 2 * dim;
shapeSurfaceImage = zeros(dim, dim);
alpha = contrastRatio / double(numSamples);

for i = 1:numSamples
    tsdf = shapeSamples{i}.tsdf;
    tsdfGrid = reshape(tsdf, gridDim, gridDim);
    tsdfBig = imresize(tsdfGrid, 2);
    
    % find surface...
    tsdfThresh = tsdfBig > 0;
    SE = strel('square', 3);
    I_d = imdilate(tsdfThresh, SE);
    
    % create border masks
    insideMaskOrig = (tsdfThresh == 0);
    outsideMaskDi = (I_d == 1);
    tsdfSurface = double(~(outsideMaskDi & insideMaskOrig));
    
%     shapeSurfaceIndices = find(abs(tsdfBig) < shapeParams.surfaceThresh);
%     tsdfSurface = ones(dim, dim);
%     tsdfSurface(shapeSurfaceIndices) = 0;
%     
    if vis
        figure(100);
        H = high_res_surface(tsdfSurface, scale);
        imshow(tsdfSurface);
        pause(0.5);
    end
%     size(tsdfSurface)
%     size(shapeSurfaceImage)
    
    shapeSurfaceImage = shapeSurfaceImage + alpha * tsdfSurface;
end
shapeSurfaceImage = shapeSurfaceImage + (1.0 - contrastRatio) * zeros(dim, dim);

% figure;
% subplot(1,4,1);
% w = shapeSurfaceImage.^3;
% imshow(w);
% 
% subplot(1,4,2);
% f = histeq(shapeSurfaceImage, 100);
% x = f;
% x(x == 0) = 5e-3; % remove 0 values
% G = fspecial('gaussian',[5 5], 0.5);
% y = imfilter(x, G, 'same');
% a = y.^0.15;
% imshow(a);
% 
% subplot(1,4,3);
% G = fspecial('gaussian',[5 5], 0.5);
% Ig = imfilter(shapeSurfaceImage, G, 'same');
% fp = histeq(Ig,100);
% imshow(fp);
% 
% subplot(1,4,4);
% q = 0.6*w + 0.4*a;
% imshow(q);

gamma = 3;
beta = 0.15;
sig = 0.5;
nbins = 100;
blend = 0.6;
siContrastEnhanced = shapeSurfaceImage.^gamma;
siEqualized = histeq(shapeSurfaceImage, nbins);
siEqualized(siEqualized == 0) = 5e-3; % remove 0 values
G = fspecial('gaussian',[5 5], sig);
siEqualizedFilt = imfilter(siEqualized, G, 'same');
siEqFlat = siEqualizedFilt.^beta;

shapeSurfaceImage = blend * siContrastEnhanced + (1 - blend) * siEqFlat;
%shapeSurfaceImage = high_res_gpis(shapeSurfaceImage, scale / 2);
% figure;
% imshow(shapeSurfaceImage);

% normalize the values to 0 and 1
% shapeSurfaceImage =apeSurfaceImage - min(min(shapeSurfaceImage))) / ...
%     (max(max(sha (shpeSurfaceImage)) - min(min(shapeSurfaceImage)));

if black
    shapeSurfaceImage = max(max(shapeSurfaceImage))*ones(hd_dim, hd_dim) - shapeSurfaceImage;
end

if false
    figure(4);
    % subplot(1,2,1);
    % imshow(shapeImageScaled);
    % title('Avg Scaled Tsdfs');
    % subplot(1,2,2);
    imshow(shapeSurfaceImage);
    %title('Avg Tsdf Zero Crossings');
end
end
