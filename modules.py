# execfile('params.py')
execfile('mylogging.py')

def replaceCheck(dir1, dir2):
    if os.path.exists(dir1):
        print('\n')
        ovr = raw_input('Directory already exists. Overwrite? (y/n): ')
        print('\n')
        if ovr in ('y', 'Y'):
            shutil.rmtree(dir1)
            shutil.copytree(dir2, dir1)
        elif ovr in ('n', 'N'):
            print('Exiting now.')
            sys.exit(1)
    else:
        shutil.copytree(dir2, dir1)

def getCoords(image, cluster):
    ia.open(image)
    ra = np.deg2rad(float(Ned.query_object(cluster)['RA']))
    dec = np.deg2rad(float(Ned.query_object(cluster)['DEC']))
    w = [ra, dec]
    x0 = np.round(ia.topixel(w)['numeric'][0])
    y0 = np.round(ia.topixel(w)['numeric'][1])
    ia.close()
    return x0, y0

def freqInfo(vis):
    '''
    Function to print all the frequencies in a visibility spectral window 
    INPUT : visibility file
    OUTPUT: array of all frequencies in the spectral window
    '''
    msmd.open(vis)
    freq = msmd.chanfreqs(0)
    msmd.done()
    return freq


def createHalo(imageref, centre_x, centre_y, size, totflux, ftype):
    '''
    Function to create a halo of given flux at reference frequency of input image
    INPUT:
            imageref: input image without halo
            centre_x: x position where halo should be added
            centre_y: y position where halo should be added
            size	: size of the halo (in pixels)
            totflux	: total flux of the halo
            ftype	: type of spatial distribution in halo
                    'gaussian'		: I(r) = I0/(sig*sqrt(2*pi))*exp((x-x0)**2+(y-y0)**2/(2*sig**2)) 
                                                            (sig=FWHM/(2*sqrt(2ln2)) where FWHM=Halo Diameter)
                    'polynomial'	: I(r) = -0.719*r**2 + 1.867*r - 0.141 (r = Normalized Distance)
                    'exponential'	: I(r) = I0 * exp(r/re) [re = 2.6 * Rh] (Rh = Halo Radius)
    OUTPUT:
            output image with halo
    '''
    ref_halo = '.'.join(imageref.split('.')[:-1]) + '_reffreq_flux_{:f}Jy_{}.image'.\
        format(totflux, ftype)
    logger.info('Creating halo image - {}'.format(ref_halo.split('/')[-1]))
    replaceCheck(ref_halo, imageref)

    ia.open(ref_halo)
    image_x = imhead(ref_halo)['shape'][0]
    image_y = imhead(ref_halo)['shape'][1]
    newim = np.zeros([image_x, image_y])
    Y, X = np.meshgrid(np.arange(image_y), np.arange(image_x))
    if ftype == 'G':
        rh = size/(2.0*np.sqrt(2.0*np.log(2.0)))
        g = Gaussian2D(totflux/(rh*np.sqrt(2*np.pi)),
                       centre_x, centre_y, rh, rh)
        newim = g(X, Y)
    elif ftype == 'P':
        rh = size/2.
        p = Polynomial1D(2, c0=-0.141, c1=1.867, c2=-0.719)
        Z = np.sqrt((X-centre_x)**2 + (Y-centre_y)**2)
        newim = totflux * p(Z/rh)
    elif ftype == 'E':
        rh = size/2.
        e = ExponentialCutoffPowerLaw1D(
            amplitude=totflux, alpha=0.0, x_cutoff=rh/2.6)
        Z = np.sqrt((X-centre_x)**2 + (Y-centre_y)**2)
        newim = e(Z)
    logger.debug('{: <30s}{: >15f}'.format('Unnormalised Total flux:',np.sum(newim)))
    ratio = totflux/np.sum(newim)
    beam2 = ratio*newim
    logger.debug('{: <30s}{: >15f}'.format('Scaled Total Flux:',np.sum(beam2)))
    ia.putchunk(beam2)
    # logger.info('Created halo with total flux density [[{:f} mJy]] and profile [[{}]] \
# at redshift [[z={}]] with size [[{:.2f} Mpc]].\n'.format(totflux*1.e3, ftype, z, l/1.e3))
    logger.info('Created halo image with total flux density [{:.2f} mJy]\n'.format(totflux*1.e3))
    ia.close()
    return ref_halo


def addHaloVis(msfile, halofile, flux, spix):
    '''
    Function to add artificial halo to source visibilities 
    INPUT:
            msfile	: visiblity file
            halofile: halo image file 
            spix	: spectral index of halo to be assumed
    OUTPUT:
            visibility file with halo added 
    '''
    freq = freqInfo(msfile)

    myms = '.'.join(msfile.split('.')[:-1]) + \
        '_wHalo_flux_{:f}.MS'.format(flux)
    logger.info('Creating modified visibility file - {}'.format(myms.split('/')[-1]))
    replaceCheck(myms, msfile)

    reffreq = np.max([imhead(imgpath)['refval'][2],
                      imhead(imgpath)['refval'][3]])
    logger.debug('Halo Reference frequency 	= {:.2f} MHz'.format(reffreq/1.e6))
    logger.info('Scaling halo flux to spw frequencies...')

    for j, f in enumerate(freq):
        try:
            newhalo = 'haloimg_freq_{:.2f}_flux_{:.1f}.image'.format(
                f/1.e6, flux)
            expr = 'IM0*' + str(f/reffreq) + '^' + str(spix)
            immath(imagename=halofile, expr=expr, outfile=newhalo)
            default(ft)
            # ft(vis=myms, model=newhalo, spw='0:'+str(j), incremental=True, usescratch=True)
            ft(vis=myms, model=newhalo, spw='0:'+str(j), usescratch=True)
            shutil.rmtree(newhalo)
        except Exception as e:
            logger.error('Something went wrong. Check for error!')
            logger.error(e)
            break
    default(uvsub)
    uvsub(vis=myms, reverse=True)
    logger.info('Done!')
    logger.info('Visibility file with halo created!\n')
    return myms


def cleanup(loc):
    from glob import glob
    extns = ['psf', 'flux', 'pb', 'sumwt', 'mask', 'model']
    to_be_deleted = [fname for extn in extns for fname in glob(loc+'/*.'+extn)]
    for f in to_be_deleted:
        try:
            shutil.rmtree(f)
        except Exception as e:
            logger.error(e)


def getStats(image, x0, y0, radius):
    r = str(radius) + 'arcsec'
    ia.open(image)
    ra = ia.toworld([x0, y0], 's')['string'][0]
    dec = ia.toworld([x0, y0], 's')['string'][1]
    reg = 'circle[[{}, {}], {}]'.format(ra, dec, r)
    stats = imstat(imagename=image, region=reg, axes=[0, 1])
    ia.close()
    return stats


def myConvolve(image, output, bopts):
    if bopts == 'beam':
        bmaj = bparams[0]
        bmin = bparams[1]
        bpa = bparams[2]
    elif bopts == 'factor':
        bmaj = smooth_f * \
            imhead(image)['restoringbeam']['major']['value']*3600.
        bmin = smooth_f * \
            imhead(image)['restoringbeam']['minor']['value']*3600.
        bpa = imhead(image)['restoringbeam']['positionangle']['value']
    elif bopts == 'num_of_beams':
        bmaj = np.round(np.sqrt((2*radius)**2/nbeams))
        bmin = bmaj
        bpa = 0.0
    default(imsmooth)
    imsmooth(imagename=image, targetres=True, major=qa.quantity(bmaj, 'arcsec'),
             minor=qa.quantity(bmin, 'arcsec'), pa=qa.quantity(bpa, 'deg'), outfile=output, overwrite=True)
    return output


def estimateRMS(image, x0, y0, radius):
    logger.info('Estimating RMS in {} around ({}, {}) with radius {:.2f}\'\n...'.
          format(image.split('/')[-1], x0, y0, radius/60.))
    fitsfile = '.'.join(image.split('.')[:-1]) + '.fits'
    exportfits(imagename=image, fitsimage=fitsfile, overwrite=True)
    subprocess.call([bane_pth, fitsfile])
    rmsfile = '.'.join(image.split('.')[:-1]) + '_rms.fits'
    bkgfile = '.'.join(image.split('.')[:-1]) + '_bkg.fits'
    rmsimage = '.'.join(image.split('.')[:-1]) + '_rms.image'
    importfits(fitsimage=rmsfile, imagename=rmsimage, overwrite=True)
    rms = getStats(rmsimage, x0, y0, radius)['rms'][0]
    os.remove(fitsfile)
    os.remove(rmsfile)
    os.remove(bkgfile)
    shutil.rmtree(rmsimage)
    logger.info('RMS estimated to be {:.3f} mJy/beam.\n'.format(rms*1.e3))
    return rms


def run_imaging(task, output):
    logger.info('Running deconvolution using task {}:'.format(task))
    if task =='tclean':
        default(tclean)
        tclean(vis=newvis, imagename=output, niter=N, threshold=thresh, deconvolver=dcv,
               scales=scle, imsize=isize, cell=csize, weighting=weight, robust=rbst,
               gridder=grdr, wprojplanes=wproj,
               savemodel='modelcolumn', aterm=False, pblimit=0.0, wbawp=False)
    elif task == 'wsclean':
        chgc_command = 'chgcentre -f -minw -shiftback {}'.format(newvis)
        subprocess.call(chgc_command.split())
        clean_command = 'wsclean -mem 25 -name {} -weight {} {} -size {} {} -scale {} -niter {} -auto-threshold {} -multiscale -multiscale-scale-bias 0.7 -pol RR {}'.format(
            output, weight, rbst, isize, isize, cell/3600, N, thresh_f, newvis)
        subprocess.call(clean_command.split())

